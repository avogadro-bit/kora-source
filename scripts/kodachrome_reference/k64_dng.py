#!/usr/bin/env python3
"""Étape 2 : appliquer les courbes caractéristiques K64 à un RAW DNG.

Exemple : python k64_dng.py photo.dng --out resultat --ev 0

Modèle volontairement simple : canaux sRGB LINÉAIRES -> exposition relative
conventionnelle -> densités Status A -> transmissions assimilées à du RGB.
Les deux assimilations RGB/film sont des HYPOTHÈSES, pas une caractérisation
spectrale du K64. Ce programme n'utilise ni MTF, ni grain, ni spectres.

Sections 1 à 7 : les étapes du calcul, dans l'ordre. Voir GUIDE.txt.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.metadata
import json
from pathlib import Path

import numpy as np
import rawpy
import tifffile
from PIL import Image, ImageCms

HERE = Path(__file__).resolve().parent
CHANNELS = ('R', 'G', 'B')
Y_WEIGHTS = np.array([0.2126, 0.7152, 0.0722])


# 1. CHARGER LES COURBES EXTRAITES, SANS LES MODIFIER
def read_curves(csv_path: Path):
    """Accepte characteristic.csv ou characteristic_grid.csv de l'étape 1."""
    values = {c: [] for c in CHANNELS}
    with csv_path.open(encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        required = {'curve', 'log10_exposure_lux_s', 'density_status_A'}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError('Le CSV doit contenir curve, log10_exposure_lux_s et density_status_A.')
        for row in reader:
            c = row['curve']
            if c not in values:
                raise ValueError(f'Courbe inattendue : {c}. Utiliser les caractéristiques R/G/B.')
            values[c].append((float(row['log10_exposure_lux_s']), float(row['density_status_A'])))
    curves = {}
    for c, pairs in values.items():
        a = np.array(sorted(pairs), dtype=np.float64)
        if len(a) < 2 or not np.isfinite(a).all():
            raise ValueError(f'Courbe {c} absente, incomplète ou non finie.')
        x, d = a.T
        if np.any(np.diff(x) <= 0) or np.any(d < 0):
            raise ValueError(f'Abscisses non uniques ou densité négative dans {c}.')
        curves[c] = (x, d)
    return curves


# 2. DÉVELOPPER LE DNG EN RGB LINÉAIRE
def develop_dng(path: Path, wb: str = 'camera', half_size: bool = False):
    """LibRaw : niveaux noir/blanc, balance des blancs, dématriçage, matrice couleur.

    gamma=(1,1) évite un encodage non linéaire avant les courbes Kodak.
    On conserve la mise à l'échelle du capteur, mais pas l'éclaircissement auto.
    Ce RGB relatif et borné n'est PAS une mesure absolue en lux.s.
    """
    with rawpy.imread(str(path)) as raw:
        camera_wb = list(raw.camera_whitebalance)
        if wb == 'camera' and not all(np.isfinite(v) and v > 0 for v in camera_wb[:3]):
            raise ValueError('Balance des blancs appareil absente. Essayer --wb daylight.')
        info = {
            'black_levels': list(raw.black_level_per_channel),
            'white_level': int(raw.white_level),
            'camera_wb': camera_wb,
            'wb_requested': wb,
            'color_description': raw.color_desc.decode('ascii', errors='replace'),
            'raw_visible_size': [int(raw.sizes.height), int(raw.sizes.width)],
        }
        rgb16 = raw.postprocess(
            output_color=rawpy.ColorSpace.sRGB,
            output_bps=16,
            gamma=(1.0, 1.0),
            use_camera_wb=(wb == 'camera'),
            use_auto_wb=False,
            no_auto_bright=True,
            adjust_maximum_thr=0.0,
            no_auto_scale=False,
            bright=1.0,
            highlight_mode=rawpy.HighlightMode.Clip,
            half_size=half_size,
        )
        applied = getattr(raw, 'auto_whitebalance', None)
        info['applied_wb_if_available'] = None if applied is None else list(applied)
    if rgb16.ndim != 3 or rgb16.shape[2] != 3 or rgb16.dtype != np.uint16:
        raise ValueError('Le décodeur doit produire trois canaux RGB 16 bits.')
    # Ce comptage concerne la sortie LibRaw, pas une mesure de saturation capteur.
    info['libraw_output_at_zero_fraction_rgb'] = np.mean(rgb16 == 0, axis=(0, 1)).tolist()
    info['libraw_output_at_65535_fraction_rgb'] = np.mean(rgb16 == 65535, axis=(0, 1)).tolist()
    return rgb16.astype(np.float32) / 65535.0, info


# 3. CHOISIR UN REPÈRE D'EXPOSITION COMMUN AUX TROIS CANAUX
def gray_anchor(curves, target_y: float = 0.18):
    """Convention d'affichage : gris d'entrée -> luminance de transmission 0,18.

    Un SEUL logH de référence commun, calculé sur les courbes. Aucun ajustement
    par image, aucune égalisation indépendante R/G/B. Les dominantes subsistent.
    Les poids sRGB sont ici eux-mêmes une hypothèse du modèle d'affichage.
    """
    lo = max(x[0] for x, d in curves.values())
    hi = min(x[-1] for x, d in curves.values())

    def y_at(logh):
        t = np.array([10.0**(-np.interp(logh, *curves[c])) for c in CHANNELS])
        return float(t @ Y_WEIGHTS)

    if not y_at(lo) < target_y < y_at(hi):
        raise ValueError('La luminance de référence est hors du domaine des courbes.')
    # Vérification de la monotonie avant la recherche dichotomique.
    probe = np.linspace(lo, hi, 4096)
    ys = sum(w * 10**(-np.interp(probe, *curves[c])) for c, w in zip(CHANNELS, Y_WEIGHTS))
    if np.any(np.diff(ys) < -1e-10):
        raise ValueError('Courbes non monotones : fournir explicitement --logh-gray.')
    for _ in range(64):
        mid = (lo + hi) / 2
        if y_at(mid) < target_y:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


# 4. EXPOSITION RELATIVE -> DENSITÉ KODAK -> TRANSMISSION
def apply_curves(rgb, curves, logh_gray, ev=0.0, gray_input=0.18,
                 view_ev=0.0, intermediate_dir: Path | None = None):
    """logH = logH_gris + log10(RGB / gris_entree) + EV*log10(2).

    D = interpolation du CSV ; T = 10**(-D). Plus exposé -> moins dense
    -> plus lumineux : comportement d'une diapositive, pas d'un négatif.
    En dehors des courbes, on borne AUX EXTRÉMITÉS et on compte ces valeurs.
    Cette saturation est une convention du programme, pas une mesure Kodak.
    """
    if rgb.ndim != 3 or rgb.shape[-1] != 3 or not np.isfinite(rgb).all():
        raise ValueError('Une image RGB finie H×W×3 est requise.')
    if np.min(rgb) < 0 or np.max(rgb) > 1:
        raise ValueError('L’entrée doit être le RGB linéaire relatif dans [0,1].')
    if not (np.isfinite(gray_input) and gray_input > 0):
        raise ValueError('gray_input doit être strictement positif et fini.')
    if not all(np.isfinite(v) for v in (logh_gray, ev, view_ev)):
        raise ValueError('Les paramètres d’exposition doivent être finis.')
    out = np.empty_like(rgb, dtype=np.float32)
    stats = {}
    saved = {}
    if intermediate_dir is not None:
        # Fichiers sur disque : évite trois gros tableaux flottants en mémoire.
        for name in ('logh', 'density', 'transmission'):
            saved[name] = np.lib.format.open_memmap(
                intermediate_dir / (name + '.npy'), mode='w+', dtype='float32', shape=rgb.shape)
    for i, c in enumerate(CHANNELS):
        x, d = curves[c]
        low_count = high_count = clip_count = zero_count = 0
        # Traitement par bandes pour les DNG de grande taille.
        for start in range(0, rgb.shape[0], 256):
            sl = slice(start, start + 256)
            values = rgb[sl, :, i].astype(np.float64)
            zero = (values == 0)
            # Le zéro correspond à logH=-inf, conservé dans l'intermédiaire.
            with np.errstate(divide='ignore'):
                logh = logh_gray + np.log10(values / gray_input) + ev * np.log10(2.0)
            low_count += int(np.count_nonzero(logh < x[0]))
            high_count += int(np.count_nonzero(logh > x[-1]))
            zero_count += int(np.count_nonzero(zero))
            density = np.interp(np.clip(logh, x[0], x[-1]), x, d)
            transmission = 10.0**(-density)
            viewed = transmission * (2.0**view_ev)
            clip_count += int(np.count_nonzero(viewed > 1))
            out[sl, :, i] = np.clip(viewed, 0, 1)
            if saved:
                saved['logh'][sl, :, i] = logh
                saved['density'][sl, :, i] = density
                saved['transmission'][sl, :, i] = transmission
        n = rgb.shape[0] * rgb.shape[1]
        stats[c] = {
            'curve_logh_domain': [float(x[0]), float(x[-1])],
            'below_curve_fraction': low_count/n, 'above_curve_fraction': high_count/n,
            'input_zero_fraction': zero_count/n,
            'display_clipped_fraction': clip_count/n,
        }
    for array in saved.values():
        array.flush()
    return out, stats


# 5. ENCODER EN sRGB, UNE SEULE FOIS, APRÈS L'EFFET
def encode_srgb(linear):
    a = np.clip(np.asarray(linear), 0, 1)
    return np.where(a <= 0.0031308, 12.92*a, 1.055*a**(1/2.4)-0.055)


# 6. ENREGISTRER UN VRAI TIFF RGB 16 BITS AVEC PROFIL ICC
def save_tiff16(path: Path, linear, icc):
    pixels = np.rint(np.clip(encode_srgb(linear), 0, 1)*65535).astype(np.uint16)
    tifffile.imwrite(
        path, pixels, photometric='rgb', metadata=None, compression=None,
        software='k64_dng.py - approximation tonale K64',
        extratags=[(34675, 'B', len(icc), icc, False)],
    )


# 7. RASSEMBLER LES ÉTAPES ET ENREGISTRER LES PARAMÈTRES
def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('dng', type=Path, help='DNG original, lu sans modification')
    parser.add_argument('--out', type=Path, default=Path('resultat_k64'), help='Dossier de sortie')
    parser.add_argument('--curves', type=Path, default=HERE/'data/characteristic.csv')
    parser.add_argument('--ev', type=float, default=0.0, help='Décalage AVANT les courbes, en stops')
    parser.add_argument('--view-ev', type=float, default=0.0, help='Gain APRÈS les courbes, en stops')
    parser.add_argument('--gray-input', type=float, default=0.18, help='Valeur RGB linéaire de référence')
    parser.add_argument('--logh-gray', type=float, default=None, help='Repère manuel sur l’axe Kodak')
    parser.add_argument('--wb', choices=['camera', 'daylight'], default='camera')
    parser.add_argument('--half-size', action='store_true', help='Aperçu à dimensions divisées par deux')
    parser.add_argument('--save-intermediates', action='store_true', help='Sauver les tableaux .npy, volumineux')
    args = parser.parse_args()
    source = args.dng.expanduser().resolve()
    curves_path = args.curves.expanduser().resolve()
    out = args.out.expanduser().resolve()
    if not source.is_file() or source.suffix.lower() != '.dng':
        parser.error('Indiquer le chemin d’un fichier .dng existant.')
    if not curves_path.is_file():
        parser.error('CSV absent. Garder data/characteristic.csv à côté du script ou utiliser --curves.')
    if not all(np.isfinite(v) and abs(v) <= 20 for v in (args.ev, args.view_ev)):
        parser.error('--ev et --view-ev doivent être finis, entre -20 et +20.')
    if not (np.isfinite(args.gray_input) and 0 < args.gray_input <= 1):
        parser.error('--gray-input doit être dans ]0,1].')
    names = ['01_reference_srgb.tif', '02_k64_tonal_srgb.tif', '02_k64_apercu.jpg', 'diagnostic.json']
    if args.save_intermediates:
        names += ['raw_linear.npy', 'logh.npy', 'density.npy', 'transmission.npy']
    if any((out/name).exists() for name in names):
        parser.error('Des résultats existent déjà ici. Choisir un autre dossier --out.')
    curves = read_curves(curves_path)
    logh_gray = gray_anchor(curves) if args.logh_gray is None else args.logh_gray
    common_lo = max(x[0] for x, d in curves.values())
    common_hi = min(x[-1] for x, d in curves.values())
    if not (np.isfinite(logh_gray) and common_lo <= logh_gray <= common_hi):
        parser.error('--logh-gray doit être dans le domaine commun des courbes.')

    print('1/4 Développement du DNG en RGB linéaire…')
    rgb, raw_info = develop_dng(source, args.wb, args.half_size)
    out.mkdir(parents=True, exist_ok=True)
    if args.save_intermediates:
        np.save(out/'raw_linear.npy', rgb)
    print(f'2/4 Courbes Kodak : repère logH du gris = {logh_gray:.4f}, exposition = {args.ev:+.2f} EV')
    result, stats = apply_curves(rgb, curves, logh_gray, args.ev, args.gray_input,
                                args.view_ev, out if args.save_intermediates else None)
    print('3/4 Encodage sRGB et export des TIFF 16 bits…')
    icc = ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()
    save_tiff16(out/'01_reference_srgb.tif', rgb, icc)
    save_tiff16(out/'02_k64_tonal_srgb.tif', result, icc)
    preview = Image.fromarray(np.rint(np.clip(encode_srgb(result), 0, 1)*255).astype(np.uint8))
    preview.thumbnail((2400, 2400))
    preview.save(out/'02_k64_apercu.jpg', quality=95, subsampling=0, icc_profile=icc)
    params = {'exposure_ev': args.ev, 'view_ev': args.view_ev, 'gray_input': args.gray_input,
              'logh_gray': logh_gray, 'anchor_automatic': args.logh_gray is None,
              'half_size': args.half_size, 'intermediates_saved': args.save_intermediates}
    report = {
        'model': 'K64 tonal RGB proxy; not a spectral or validated colorimetric film model',
        'input_dng': str(source), 'curves_csv': str(curves_path),
        'curves_sha256': hashlib.sha256(curves_path.read_bytes()).hexdigest(),
        'kodak_source': 'E-88, June 2009, page 4, F002_0490AC',
        'source_pdf_sha256': '484aa096910b000231c40ee57e75a0a20d7b525be6903aa3a4523ddcdca53ef0',
        'parameters': params, 'raw_development': raw_info, 'curve_domain_and_clipping': stats,
        'output_size': list(result.shape), 'output_encoding': 'sRGB encoded, 16-bit RGB TIFF, embedded sRGB ICC',
        'reference_definition': 'Same DNG development, no K64 curves, no --ev or --view-ev applied',
        'assumptions': [
            'Relative linear sRGB channels act as film exposure proxies.',
            'Status A channel transmissions are interpreted as linear display RGB.',
            'Default anchor maps input neutral 0.18 to output luminance 0.18 before view gain.',
            'One common anchor; no separate neutralization or normalization of channel endpoints.',
            'Out-of-domain exposures are clamped to curve endpoints, not extrapolated.',
            'LibRaw 16-bit sRGB output is bounded and may lose highlights and out-of-gamut colors.',
        ],
        'excluded': ['MTF', 'grain', 'spectral sensitivity', 'spectral dye density'],
        'versions': {p: importlib.metadata.version(p) for p in ('rawpy', 'numpy', 'tifffile', 'Pillow')},
        'libraw_version': list(rawpy.libraw_version),
    }
    (out/'diagnostic.json').write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    print('4/4 Terminé :', out)
    for c in CHANNELS:
        s = stats[c]
        print(f"  {c} : {s['below_curve_fraction']:.2%} sous le tracé, "
              f"{s['above_curve_fraction']:.2%} au-dessus, "
              f"{s['display_clipped_fraction']:.2%} écrêtés à l’affichage")


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, rawpy.LibRawError) as exc:
        raise SystemExit(f'Erreur : {exc}') from exc
