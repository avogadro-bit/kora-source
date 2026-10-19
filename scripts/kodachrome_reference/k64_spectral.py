"""Étape 3 : modèle de colorants, sous hypothèses explicites (voir GUIDE.txt).

D_spectral(lambda) = aC*qC(lambda) + aM*qM(lambda) + aJ*qJ(lambda)
T(lambda) = 10**(-D_spectral(lambda)). Les a sont relatifs, pas des masses.
Les densités Status A servent à ajuster aC/aM/aJ sur une exposition commune.
Le passage à une photo suppose ensuite des couches indépendantes R->C,
G->M, B->J : ce n'est PAS une caractérisation spectrale du capteur/film.
"""
from pathlib import Path
import csv
import numpy as np
from scipy.optimize import least_squares
from scipy.ndimage import map_coordinates

from k64_dng import read_curves, gray_anchor, encode_srgb

HERE = Path(__file__).resolve().parent
DYES = ('cyan', 'magenta', 'yellow')
BRADFORD = np.array([[.8951,.2664,-.1614],[-.7502,1.7135,.0367],[.0389,-.0685,1.0296]])
WHITE_D65 = np.array([.3127/.3290, 1., (1-.3127-.3290)/.3290])


def xyz_to_rgb_matrix():
    xy = np.array([[.64,.33],[.30,.60],[.15,.06]])
    columns = np.vstack((xy[:,0]/xy[:,1], np.ones(3), (1-xy.sum(axis=1))/xy[:,1]))
    return np.linalg.inv(columns * np.linalg.solve(columns, WHITE_D65))


XYZ_TO_RGB = xyz_to_rgb_matrix()


def read_dyes(path):
    groups = {name: [] for name in (*DYES, 'visual_neutral')}
    with Path(path).open(newline='', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            groups[row['curve']].append((float(row['wavelength_nm']), float(row['diffuse_spectral_density'])))
    result = {}
    for name, pairs in groups.items():
        a = np.array(sorted(pairs))
        if a.ndim != 2 or a.shape[0] < 2 or not np.isfinite(a).all() or np.any(np.diff(a[:,0]) <= 0):
            raise ValueError(f'Courbe de colorant incorrecte : {name}')
        result[name] = a
    return result


def sample_dye(points, wavelength, tails):
    """Linéaire dans le tracé ; extensions explicitement hypothétiques.

    hold = garder les valeurs de bord ; fade = aller vers zéro à 360/830 nm.
    Le léger D<0 du dessin jaune est borné à zéro DANS LE MODÈLE seulement.
    Le fichier source reste inchangé.
    """
    x, d = points.T
    d = np.maximum(d, 0)
    if tails == 'fade':
        x, d = np.r_[360., x, 830.], np.r_[0., d, 0.]
    elif tails != 'hold':
        raise ValueError('tails doit valoir hold ou fade.')
    return np.interp(wavelength, x, d)


def illuminant_weights(wavelength, cmf, illuminant):
    # Quadrature trapézoïdale explicite sur une grille à 1 nm.
    delta = np.gradient(wavelength)
    delta[[0,-1]] *= .5
    weighted = cmf * (illuminant*delta)[:,None]
    return weighted / weighted[:,1].sum()


def adapt_matrix(source_white):
    """Adaptation de l'illuminant seul ; aucun équilibrage du film ou de la photo."""
    return np.linalg.inv(BRADFORD) @ np.diag((BRADFORD@WHITE_D65)/(BRADFORD@source_white)) @ BRADFORD


class SpectralModel:
    def __init__(self, tails='hold', data_dir=None, fit_points=513):
        self.data_dir = Path(data_dir) if data_dir else HERE/'data'
        self.tails = tails
        self.curves = read_curves(self.data_dir/'characteristic.csv')
        self.anchor = gray_anchor(self.curves)  # Même exposition que l'étape 2.
        self.source_dyes = read_dyes(self.data_dir/'dyes.csv')
        cmf = np.loadtxt(self.data_dir/'source/CIE_xyz_1931_2deg.csv', delimiter=',')
        d65 = np.loadtxt(self.data_dir/'source/CIE_std_illum_D65.csv', delimiter=',')
        self.wavelength = cmf[:,0]
        self.q = np.column_stack([sample_dye(self.source_dyes[n], self.wavelength, tails) for n in DYES])
        self.visual_neutral = sample_dye(self.source_dyes['visual_neutral'], self.wavelength, tails)
        self.xyz_weights = illuminant_weights(self.wavelength, cmf[:,1:], np.interp(self.wavelength, d65[:,0], d65[:,1]))
        self.white_xyz = self.xyz_weights.sum(axis=0)
        self.rgb_weights = self.xyz_weights @ adapt_matrix(self.white_xyz).T @ XYZ_TO_RGB.T
        # 3200 K dans Kodak n'identifie pas un spectre unique : corps noir
        # choisi uniquement pour un contrôle approximatif, pas comme vérité Kodak.
        metres = self.wavelength * 1e-9
        blackbody = 1/(metres**5 * np.expm1(.01438776877/(metres*3200)))
        self.xyz_weights_3200 = illuminant_weights(self.wavelength, cmf[:,1:], blackbody)
        status = np.loadtxt(self.data_dir/'status_a.csv', delimiter=',', skiprows=1)
        responses = np.column_stack([np.interp(self.wavelength, status[:,0], status[:,i]) for i in (1,2,3)])
        # Tables de pondération complètes : ne PAS les multiplier par D65.
        self.status_weights = responses / responses.sum(axis=0)
        lo = max(x[0] for x,d in self.curves.values())
        hi = min(x[-1] for x,d in self.curves.values())
        self.logh = np.linspace(lo, hi, fit_points)
        self.target_density = np.column_stack([np.interp(self.logh, *self.curves[c]) for c in 'RGB'])
        self.amounts = np.empty((fit_points,3))
        previous = np.ones(3)
        for i, target in enumerate(self.target_density):
            fit = least_squares(lambda a: self.status_density(a)-target, previous,
                                jac=self.status_jacobian, bounds=(0, np.inf),
                                ftol=1e-11, xtol=1e-11, gtol=1e-11, max_nfev=100)
            if not fit.success:
                raise RuntimeError(f'Ajustement des colorants échoué à logH={self.logh[i]}')
            self.amounts[i] = previous = fit.x
        self.fitted_density = self.status_density(self.amounts)
        self.fit_max_residual = float(np.max(np.abs(self.fitted_density-self.target_density)))
        if self.fit_max_residual > .02:
            raise RuntimeError(f'Incompatibilité du modèle avec les courbes : résidu {self.fit_max_residual:.4f} D')
        self.lut = None

    def transmission(self, amounts):
        a = np.asarray(amounts, dtype=float)
        if a.shape[-1] != 3 or not np.isfinite(a).all() or np.any(a < 0):
            raise ValueError('Trois quantités de colorants positives ou nulles et finies sont requises.')
        return 10**(-(a @ self.q.T))

    def status_density(self, amounts):
        return -np.log10(self.transmission(amounts) @ self.status_weights)

    def status_jacobian(self, amounts):
        t = self.transmission(amounts)
        return (self.status_weights.T @ (t[:,None]*self.q))/(t@self.status_weights)[:,None]

    def integrate(self, amounts):
        """sRGB LINÉAIRE non borné : les valeurs hors gamut sont conservées ici."""
        return self.transmission(amounts) @ self.rgb_weights

    def amounts_for_rgb(self, rgb, ev=0):
        rgb = np.asarray(rgb)
        if rgb.shape[-1] != 3 or not np.isfinite(rgb).all() or rgb.min() < 0 or rgb.max() > 1:
            raise ValueError('RGB linéaire fini, dans [0,1], attendu.')
        if not np.isfinite(ev) or abs(ev) > 20:
            raise ValueError('EV doit être fini, dans [-20,20].')
        with np.errstate(divide='ignore'):
            logh = self.anchor + np.log10(rgb.astype(np.float64)/.18) + ev*np.log10(2)
        amounts = np.empty_like(logh)
        for i in range(3):
            amounts[...,i] = np.interp(logh[...,i], self.logh, self.amounts[:,i])
        return amounts

    def direct_rgb(self, rgb, ev=0):
        return self.integrate(self.amounts_for_rgb(rgb, ev))

    def build_lut(self, size=65):
        if size not in (33,65,129):
            raise ValueError('Taille de LUT : 33, 65 ou 129.')
        self.lut_size = size
        self.lut_max = self.amounts.max(axis=0)*1.000001
        axes = [np.linspace(0, v, size) for v in self.lut_max]
        grid = np.stack(np.meshgrid(*axes, indexing='ij'), axis=-1).reshape(-1,3)
        values = np.empty_like(grid, dtype=np.float32)
        for start in range(0,len(grid),2048):
            values[start:start+2048] = self.integrate(grid[start:start+2048])
        self.lut = values.reshape(size,size,size,3)
        # Une LUT numérique n'ajoute aucune donnée physique ; erreur contrôlée.
        rng = np.random.default_rng(6403)
        sample = rng.uniform(0,1,(4096,3))*self.lut_max
        exact = self.integrate(sample)
        fast = self.lookup(sample)
        errors = np.abs(fast-exact)
        display_errors = np.abs(encode_srgb(fast)-encode_srgb(exact))
        self.lut_check = {'sample_count':4096, 'seed':6403,
                          'max_abs_linear_rgb_error':float(errors.max()),
                          'p99_abs_linear_rgb_error':float(np.percentile(errors,99)),
                          'max_abs_encoded_srgb_error':float(display_errors.max())}
        return self.lut_check

    def lookup(self, amounts):
        if self.lut is None:
            raise RuntimeError('Construire la LUT avant son utilisation.')
        a = np.asarray(amounts)
        if np.any(a < 0) or np.any(a > self.lut_max*(1+1e-8)) or not np.isfinite(a).all():
            raise ValueError('Quantités hors domaine de LUT.')
        coords = (a.reshape(-1,3)/self.lut_max*(self.lut_size-1)).T
        return np.column_stack([map_coordinates(self.lut[...,i],coords,order=1,
                                                prefilter=False,mode='nearest') for i in range(3)]).reshape(a.shape)

    def apply(self, rgb, ev=0, view_ev=0):
        if not np.isfinite(view_ev) or abs(view_ev) > 20:
            raise ValueError('Gain après courbes invalide.')
        result = np.empty_like(rgb, dtype=np.float32)
        low = high = outside_low = outside_high = 0
        n = int(np.prod(rgb.shape[:-1]))
        flat_in, flat_out = rgb.reshape(-1,3), result.reshape(-1,3)
        for start in range(0,n,65536):
            block = flat_in[start:start+65536]
            a = self.amounts_for_rgb(block, ev)
            value = self.lookup(a)*2**view_ev
            low += int(np.count_nonzero(np.any(value < 0,axis=1)))
            high += int(np.count_nonzero(np.any(value > 1,axis=1)))
            with np.errstate(divide='ignore'):
                h = self.anchor+np.log10(block.astype(np.float64)/.18)+ev*np.log10(2)
            outside_low += int(np.count_nonzero(np.any(h<self.logh[0],axis=1)))
            outside_high += int(np.count_nonzero(np.any(h>self.logh[-1],axis=1)))
            flat_out[start:start+len(block)] = np.clip(value,0,1)
        return result, {'below_zero_srgb_any_fraction':low/n, 'above_one_srgb_any_fraction':high/n,
                        'below_curve_any_fraction':outside_low/n, 'above_curve_any_fraction':outside_high/n}

    def diagnostics(self):
        known = (self.wavelength >= 420) & (self.wavelength < 700)
        t_neutral = 10**(-self.visual_neutral)
        mix = self.transmission(np.ones(3))
        def visual_density(t, weights):
            return float(-np.log10(t@weights[:,1]))
        return {'tails':self.tails, 'spectral_domain_nm':[360,830], 'step_nm':1,
                'dye_source_domain_nm':[float(self.source_dyes['cyan'][0,0]),float(self.source_dyes['cyan'][-1,0])],
                'raw_dye_min_density':{k:float(v[:,1].min()) for k,v in self.source_dyes.items()},
                'unit_mix_minus_published_neutral_max_D_known_domain':float(np.max(np.abs(self.q[known].sum(axis=1)-self.visual_neutral[known]))),
                'status_A_fit_max_abs_D_residual':self.fit_max_residual,
                'amount_min_CMY':self.amounts.min(axis=0).tolist(),
                'amount_max_CMY':self.amounts.max(axis=0).tolist(),
                'amount_increasing_steps_CMY':(np.diff(self.amounts,axis=0)>1e-6).sum(axis=0).tolist(),
                'white_D65_XYZ':self.white_xyz.tolist(),
                'illuminant_white_only_rgb':self.integrate(np.zeros(3)).tolist(),
                'unit_mix_visual_D_D65':visual_density(mix,self.xyz_weights),
                'unit_mix_visual_D_blackbody3200':visual_density(mix,self.xyz_weights_3200),
                'published_neutral_visual_D_blackbody3200':visual_density(t_neutral,self.xyz_weights_3200),
                'D65_white_XYZ_weight_outside_dye_domain_fraction':(self.xyz_weights[~known].sum(axis=0)/self.xyz_weights.sum(axis=0)).tolist(),
                'lut':getattr(self,'lut_check',None)}
