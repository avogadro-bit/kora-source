"""Éclairage d'observation indépendant du modèle scène/film des étapes 3–6.

La reconstruction et les réponses des couches restent sous D65. Les quantités
de colorants sont calculées une fois puis observées sous D65 ou D50, à Y blanc
égal. Bradford adapte le blanc de la lampe vers le blanc sRGB, sans neutraliser
la transmission du film. Ce choix suppose une adaptation visuelle complète.
"""
import hashlib
import numpy as np
from scipy.ndimage import map_coordinates
from k64_spectral import illuminant_weights, adapt_matrix, XYZ_TO_RGB
from k64_dng import encode_srgb
from k64_reconstruction import lab_from_linear_rgb, delta_e76

VIEWING_LIGHTS = ('D65', 'D50')


def require_scene_d65(scene_illuminant):
    if scene_illuminant != 'D65':
        raise ValueError("La scène virtuelle reste D65 dans cette étape ; seul l'éclairage d'observation varie.")


class ObservationRenderer:
    """Intégration et LUT propres à une lampe ; aucun changement du film partagé."""
    def __init__(self, film, illuminant='D65'):
        if illuminant not in VIEWING_LIGHTS:
            raise ValueError('Observation : D65 ou D50.')
        self.film = film
        self.illuminant = illuminant
        cmf = np.loadtxt(film.data_dir/'source/CIE_xyz_1931_2deg.csv', delimiter=',')
        table = np.loadtxt(film.data_dir/'source'/f'CIE_std_illum_{illuminant}.csv', delimiter=',')
        if table[0, 0] > film.wavelength[0] or table[-1, 0] < film.wavelength[-1]:
            raise ValueError('Domaine spectral de la lampe incomplet.')
        self.spd = np.interp(film.wavelength, table[:, 0], table[:, 1])
        self.xyz_weights = illuminant_weights(film.wavelength, cmf[:, 1:], self.spd)
        self.white_xyz = self.xyz_weights.sum(axis=0)
        self.adaptation = adapt_matrix(self.white_xyz)
        self.rgb_weights = self.xyz_weights @ self.adaptation.T @ XYZ_TO_RGB.T
        self.lut = None

    def from_transmission(self, transmission, adapted=True):
        t = np.asarray(transmission, dtype=float)
        if t.shape[-1] != len(self.film.wavelength) or not np.isfinite(t).all() or np.any((t < 0) | (t > 1)):
            raise ValueError('Transmission spectrale finie dans [0,1] attendue.')
        if adapted:
            return t @ self.rgb_weights
        return t @ self.xyz_weights @ XYZ_TO_RGB.T

    def integrate(self, amounts):
        return self.from_transmission(self.film.transmission(amounts))

    def lookup(self, amounts):
        if self.lut is None:
            raise RuntimeError('Construire la LUT de cette lampe avant son utilisation.')
        a = np.asarray(amounts)
        if a.shape[-1] != 3 or not np.isfinite(a).all() or np.any(a < 0) or np.any(a > self.lut_max*(1+1e-8)):
            raise ValueError('Quantités hors domaine de LUT.')
        coords = (a.reshape(-1, 3)/self.lut_max*(self.lut_size-1)).T
        return np.column_stack([map_coordinates(self.lut[..., c], coords, order=1,
                                prefilter=False, mode='nearest') for c in range(3)]).reshape(a.shape)

    def build_lut(self, size=65):
        if size not in (33, 65, 129):
            raise ValueError('Taille de LUT : 33, 65 ou 129.')
        self.lut_size = size
        self.lut_max = self.film.amounts.max(axis=0)*1.000001
        grid = np.stack(np.meshgrid(*[np.linspace(0, v, size) for v in self.lut_max], indexing='ij'), axis=-1).reshape(-1, 3)
        values = np.empty_like(grid, dtype=np.float32)
        for start in range(0, len(grid), 2048):
            values[start:start+2048] = self.integrate(grid[start:start+2048])
        self.lut = values.reshape(size, size, size, 3)
        samples = np.random.default_rng(6403).uniform(0, 1, (4096, 3))*self.lut_max
        exact, fast = self.integrate(samples), self.lookup(samples)
        error = np.abs(encode_srgb(fast)-encode_srgb(exact))
        self.lut_check = {'size':size, 'samples':4096, 'seed':6403,
                          'max_abs_linear_rgb_error':float(np.abs(fast-exact).max()),
                          'max_abs_encoded_srgb_error':float(error.max())}
        return self.lut_check

    def diagnostics(self):
        return {'illuminant':self.illuminant, 'white_XYZ_Y1':self.white_xyz.tolist(),
                'Bradford_to_sRGB_D65':self.adaptation.tolist(),
                'bare_illuminant_adapted_RGB':self.from_transmission(np.ones(len(self.spd))).tolist(),
                'bare_illuminant_unadapted_RGB':self.from_transmission(np.ones(len(self.spd)), False).tolist(),
                'normalization':'Y=1 for the bare illuminant; no film-base or image neutralization',
                'adaptation_assumption':'Full Bradford adaptation to the sRGB D65 white',
                'lut':getattr(self, 'lut_check', None)}


def audit_pair(film, viewers, indices, exact, fast, ev, view_ev=0):
    """Chaîne complète et erreur sur la différence D50/D65, mêmes pixels contrôlés."""
    valid = np.isfinite(exact).all(axis=1) & np.isfinite(fast).all(axis=1)
    if not np.array_equal(np.isfinite(exact).all(axis=1), np.isfinite(fast).all(axis=1)) or not valid.any():
        raise RuntimeError('Admissibilité rapide/directe incompatible ou aucun pixel de contrôle.')
    a_exact = film.amounts_for_rgb(exact[valid], ev)
    a_fast = film.amounts_for_rgb(fast[valid], ev)
    truth = {n:v.integrate(a_exact)*2**view_ev for n,v in viewers.items()}
    quick = {n:v.lookup(a_fast)*2**view_ev for n,v in viewers.items()}
    checks = {}
    for n in VIEWING_LIGHTS:
        errors = np.max(np.abs(encode_srgb(quick[n])-encode_srgb(truth[n])), axis=1)
        checks[n] = {'max_abs_encoded_srgb_error':float(errors.max()),
                     'p99_abs_encoded_srgb_error':float(np.percentile(errors, 99)),
                     'max_deltaE76_before_clip':float(delta_e76(quick[n], truth[n]).max())}
    exact_delta = lab_from_linear_rgb(truth['D50'])-lab_from_linear_rgb(truth['D65'])
    quick_delta = lab_from_linear_rgb(quick['D50'])-lab_from_linear_rgb(quick['D65'])
    # Plus informatif que la seule différence des normes : contrôle aussi la direction.
    effect_error = np.linalg.norm(quick_delta-exact_delta, axis=1)
    report = {'ev':float(ev), 'sample_count':len(indices), 'admissible_count':int(valid.sum()),
              'per_illuminant':checks, 'max_error_on_Lab_difference_vector':float(effect_error.max()),
              'p95_error_on_Lab_difference_vector':float(np.percentile(effect_error, 95))}
    rows = []
    for j, index in enumerate(np.asarray(indices)[valid]):
        rows.append({'flat_index':int(index), 'ev':float(ev),
                     **{f'fast_amount_{c}':float(a_fast[j,k]) for k,c in enumerate('CMY')},
                     **{f'exact_amount_{c}':float(a_exact[j,k]) for k,c in enumerate('CMY')},
                     'deltaE76_D50_D65_fast':float(np.linalg.norm(quick_delta[j])),
                     'deltaE76_D50_D65_direct':float(np.linalg.norm(exact_delta[j])),
                     'error_on_Lab_difference_vector':float(effect_error[j])})
    return report, rows


def sampled_exact(engine, rgb, kinds, method, sample_size=384):
    flat = np.asarray(rgb).reshape(-1, 3)
    rng = np.random.default_rng(6405)
    random = rng.choice(len(flat), min(sample_size, len(flat)), replace=False)
    targeted = np.flatnonzero(np.asarray(kinds).ravel() == 1)
    targeted = rng.choice(targeted, min(sample_size, len(targeted)), replace=False)
    indices = np.unique(np.r_[random, targeted])
    return indices, np.array([engine.exact(v, method)[0] for v in flat[indices]])


def render_pair(film, viewers, responses, ev, view_ev=0):
    """Les deux lampes reçoivent exactement le même tableau de quantités CMJ."""
    if set(viewers) != set(VIEWING_LIGHTS) or any(v.film is not film for v in viewers.values()):
        raise ValueError('Deux lampes partageant le même modèle de film sont requises.')
    if not np.isfinite(view_ev) or abs(view_ev) > 20:
        raise ValueError('Gain d’affichage invalide.')
    e = np.asarray(responses)
    flat = e.reshape(-1, 3)
    valid = np.isfinite(flat).all(axis=1)
    outputs = {n:np.full(flat.shape, np.nan, dtype=np.float32) for n in VIEWING_LIGHTS}
    amount_hash = hashlib.sha256()
    low = high = 0
    for start in range(0, len(flat), 16384):
        indices = np.flatnonzero(valid[start:start+16384])+start
        if not len(indices):
            continue
        block = flat[indices]
        # Tous les appels suivants partagent a ; aucune exposition ni correction par lampe.
        a = film.amounts_for_rgb(block, ev)
        amount_hash.update(np.asarray(a, dtype='<f8').tobytes())
        for n, viewer in viewers.items():
            outputs[n][indices] = viewer.lookup(a)*2**view_ev
        with np.errstate(divide='ignore'):
            h = film.anchor+np.log10(block/.18)+ev*np.log10(2)
        low += int(np.any(h < film.logh[0], axis=1).sum())
        high += int(np.any(h > film.logh[-1], axis=1).sum())
    count = int(valid.sum())
    shared = {'valid_pixel_count':count, 'excluded_pixel_count':int((~valid).sum()),
              'response_sha256':hashlib.sha256(np.asarray(flat, dtype='<f8').tobytes()).hexdigest(),
              'shared_amounts_sha256_valid_row_order_float64':amount_hash.hexdigest(),
              'valid_pixel_mask_sha256':hashlib.sha256(valid.tobytes()).hexdigest(),
              'below_curve_fraction_valid':low/count if count else None,
              'above_curve_fraction_valid':high/count if count else None}
    return {n:a.reshape(e.shape) for n,a in outputs.items()}, shared
