"""Étape 4 : expériences RGB -> réflectance -> réponses relatives K64.

Mire de surfaces passives virtuelles sous D65. Aucun modèle du capteur Leica.
Trois reconstructions quadratiques sous contraintes partagent le même RGB.
Elles sont des choix mathématiques, pas des spectres de scène retrouvés.
"""
from pathlib import Path
import csv
import numpy as np
from scipy.optimize import linprog, minimize, LinearConstraint
from k64_spectral import SpectralModel, XYZ_TO_RGB, WHITE_D65

HERE=Path(__file__).resolve().parent
LAYERS=('cyan_forming','magenta_forming','yellow_forming')
METHODS=('pente','courbure','ecart_gris')
LABELS={'pente':'Pente minimale','courbure':'Courbure minimale','ecart_gris':'Écart au gris minimal'}


def read_sensitivities(path):
    groups={name:[] for name in LAYERS}
    with Path(path).open(newline='',encoding='utf-8') as f:
        for row in csv.DictReader(f):
            groups[row['curve']].append((float(row['wavelength_nm']),float(row['log10_sensitivity'])))
    out={}
    for name,points in groups.items():
        a=np.array(sorted(points))
        if a.ndim!=2 or len(a)<2 or not np.isfinite(a).all() or np.any(np.diff(a[:,0])<=0):
            raise ValueError(f'Courbe incorrecte : {name}')
        out[name]=a
    return out


def sensitivity_grid(points,wavelength,tail_mode='zero'):
    """Interpolation en logS dans le domaine publié ; extensions déclarées.

    zero : S=0 hors tracé (troncature, pas une mesure Kodak).
    fade20 : S décroît linéairement à zéro sur 20 nm hors de chaque bord.
    Les unités Kodak sont énergétiques : aucun facteur photon lambda/hc ajouté.
    """
    x,log_s=points.T
    inside=(wavelength>=x[0]) & (wavelength<=x[-1])
    s=np.zeros_like(wavelength,dtype=float)
    s[inside]=10**np.interp(wavelength[inside],x,log_s)
    if tail_mode=='fade20':
        left=(wavelength<x[0]) & (wavelength>x[0]-20)
        right=(wavelength>x[-1]) & (wavelength<x[-1]+20)
        s[left]=10**log_s[0]*(wavelength[left]-(x[0]-20))/20
        s[right]=10**log_s[-1]*((x[-1]+20)-wavelength[right])/20
    elif tail_mode!='zero':
        raise ValueError('Extension des sensibilités : zero ou fade20.')
    return s,inside


def lab_from_linear_rgb(rgb):
    """CIELAB avant bornage sRGB, blanc D65. ΔE76 conditionnel au modèle."""
    xyz=np.asarray(rgb)@np.linalg.inv(XYZ_TO_RGB).T
    ratio=xyz/WHITE_D65
    delta=6/29
    f=np.where(ratio>delta**3,np.cbrt(ratio),ratio/(3*delta**2)+4/29)
    return np.stack((116*f[...,1]-16,500*(f[...,0]-f[...,1]),200*(f[...,1]-f[...,2])),axis=-1)


def delta_e76(rgb1,rgb2):
    return np.linalg.norm(lab_from_linear_rgb(rgb1)-lab_from_linear_rgb(rgb2),axis=-1)


class ReconstructionBench:
    def __init__(self,sensitivity_tails='zero',data_dir=None):
        self.data_dir=Path(data_dir) if data_dir else HERE/'data'
        self.film=SpectralModel(data_dir=self.data_dir,tails='hold')
        self.wavelength=self.film.wavelength
        self.knots=np.arange(360.,831.,10.)
        n=len(self.knots)
        # Base d'interpolation linéaire : une colonne par noeud, somme = 1.
        self.basis=np.column_stack([np.interp(self.wavelength,self.knots,np.eye(n)[i]) for i in range(n)])
        self.rgb_operator=self.film.rgb_weights.T@self.basis
        self.sensitivity_sources=read_sensitivities(self.data_dir/'sensitivity.csv')
        self.sensitivity_tails=sensitivity_tails
        self.sensitivities,self.known_domains=self._sensitivity_columns(sensitivity_tails)
        self.film_operator,self.white_response=self.response_operator(sensitivity_tails)
        self.first_difference=np.diff(np.eye(n),axis=0)
        self.second_difference=np.diff(np.eye(n),n=2,axis=0)
        d1,d2=self.first_difference,self.second_difference
        # Noeuds à pas fixe : facteurs de pas absorbés dans les poids déclarés.
        self.quadratics={
            'pente':d1.T@d1+1e-6*np.eye(n),
            'courbure':d2.T@d2+1e-3*(d1.T@d1)+1e-6*np.eye(n),
            'ecart_gris':np.eye(n),
        }

    def _sensitivity_columns(self,mode):
        pairs=[sensitivity_grid(self.sensitivity_sources[name],self.wavelength,mode) for name in LAYERS]
        return np.column_stack([p[0] for p in pairs]),np.column_stack([p[1] for p in pairs])

    def response_operator(self,mode):
        s,_=self._sensitivity_columns(mode)
        d65=np.loadtxt(self.data_dir/'source/CIE_std_illum_D65.csv',delimiter=',')
        illuminant=np.interp(self.wavelength,d65[:,0],d65[:,1])
        delta=np.gradient(self.wavelength);delta[[0,-1]]*=.5
        weights=s*(illuminant*delta)[:,None]
        white=weights.sum(axis=0)
        # Convention : toute réflectance plate r donne trois réponses r.
        # Le gain absolu des courbes est donc absorbé dans ce raccord au gris.
        return (weights/white).T@self.basis,white

    def rgb_from_reflectance(self,reflectance):
        return np.asarray(reflectance)@self.rgb_operator.T

    def responses(self,reflectance,mode=None):
        r=np.asarray(reflectance,dtype=float)
        if r.shape[-1]!=len(self.knots) or not np.isfinite(r).all() or r.min() < -1e-10 or r.max() > 1+1e-10:
            raise ValueError('Réflectance attendue : 48 valeurs finies dans [0,1].')
        operator=self.film_operator if mode is None else self.response_operator(mode)[0]
        return np.clip(r,0,1)@operator.T

    def render(self,reflectance,ev=0,view_ev=0,mode=None):
        if not np.isfinite(view_ev) or abs(view_ev)>20:
            raise ValueError('Gain invalide.')
        e=self.responses(reflectance,mode)
        # E_C,E_M,E_J sont placés dans le même ordre que les quantités C/M/J.
        # Le moteur de l'étape 3 garde son calage, seul son signal d'entrée change.
        out=self.film.direct_rgb(np.clip(e,0,1),ev=ev)*2**view_ev
        with np.errstate(divide='ignore'):
            h=self.film.anchor+np.log10(e/.18)+ev*np.log10(2)
        flags={'below_curve':np.any(h<self.film.logh[0],axis=-1),
               'above_curve':np.any(h>self.film.logh[-1],axis=-1),
               'outside_srgb':np.any((out<0)|(out>1),axis=-1)}
        return out,e,flags

    def reconstruct(self,rgb,method='pente'):
        target=np.asarray(rgb,dtype=float)
        if target.shape!=(3,) or not np.isfinite(target).all() or target.min()<0 or target.max()>1:
            raise ValueError('Fournir un triplet RGB LINÉAIRE fini dans [0,1].')
        if method not in METHODS:
            raise ValueError('Méthode inconnue.')
        q=self.quadratics[method]
        gray=float(target@np.array([.2126,.7152,.0722]))
        prior=np.full(len(self.knots),gray)
        a=self.rgb_operator
        # Solution quadratique avec égalités seules : fréquente pour couleurs douces.
        inverse_a=np.linalg.solve(q,a.T)
        candidate=prior+inverse_a@np.linalg.solve(a@inverse_a,target-a@prior)
        iterations=0;solver='equality_quadratic'
        if candidate.min() < -1e-10 or candidate.max() > 1+1e-10:
            feasible=linprog(np.zeros(len(self.knots)),A_eq=a,b_eq=target,bounds=(0,1),method='highs')
            if not feasible.success:
                raise ValueError('Ce RGB ne possède pas de réflectance admissible sur cette grille sous D65. '
                                 'La couleur n’a pas été modifiée automatiquement.')
            result=minimize(lambda r:.5*(r-prior)@q@(r-prior),feasible.x,
                            jac=lambda r:q@(r-prior),method='SLSQP',bounds=[(0,1)]*len(self.knots),
                            constraints=[LinearConstraint(a,target,target)],
                            options={'ftol':1e-12,'maxiter':1000})
            if not result.success:
                raise RuntimeError(f'Reconstruction {method} non convergée : {result.message}')
            candidate=result.x;iterations=int(result.nit);solver='bounded_SLSQP'
        # Seulement arrondis numériques aux bornes, puis contrôle de l'égalité RGB.
        candidate=np.clip(candidate,0,1)
        residual=float(np.max(np.abs(a@candidate-target)))
        if residual>1e-7:
            raise RuntimeError(f'Le RGB reconstruit ne respecte pas la cible : {residual:g}')
        return candidate,{'max_abs_rgb_residual':residual,'solver':solver,'iterations':iterations,
                          'objective':float(.5*(candidate-prior)@q@(candidate-prior))}

    def metamer_pair(self,gray=.18,max_step=.1):
        """Deux réflectances à même RGB, écart K64 extrême sous contraintes.

        Max_step limite |r[j+1]-r[j]| sur 10 nm. C'est un choix de démonstration,
        pas une distribution des objets réels ni une borne universelle.
        """
        a_ub=np.vstack((self.first_difference,-self.first_difference))
        b_ub=np.full(len(a_ub),max_step)
        candidates=[]
        for i in range(3):
            pair=[]
            for sign in (1,-1):
                solution=linprog(sign*self.film_operator[i],A_ub=a_ub,b_ub=b_ub,
                                 A_eq=self.rgb_operator,b_eq=np.full(3,gray),bounds=(0,1),method='highs')
                if not solution.success:
                    raise RuntimeError('Construction de la paire métamère impossible.')
                pair.append(solution.x)
            responses=self.responses(np.array(pair))
            span=float(np.log2(responses[1,i]/responses[0,i]))
            candidates.append((span,i,np.array(pair)))
        span,layer,pair=max(candidates,key=lambda item:item[0])
        return pair,{'gray_rgb':gray,'optimized_layer':LAYERS[layer],
                     'response_span_ev':span,'max_reflectance_step_per_10nm':max_step,
                     'max_abs_pair_rgb_difference':float(np.max(np.abs(self.rgb_from_reflectance(pair[0])-self.rgb_from_reflectance(pair[1]))))}

    def make_chart(self):
        """24 spectres artificiels connus, définis sur la même grille que l'inversion."""
        k=self.knots
        names=[];spectra=[]
        for value in (.01,.05,.18,.70):
            names.append(f'Gris {value:g}');spectra.append(np.full(len(k),value))
        for center in range(430,651,20):
            names.append(f'Bande {center}');spectra.append(.20+.45*np.exp(-.5*((k-center)/25)**2))
        variants=[('Double pic',.12+.35*np.exp(-.5*((k-450)/24)**2)+.35*np.exp(-.5*((k-625)/30)**2)),
                  ('Creux vert',.68-.48*np.exp(-.5*((k-550)/35)**2)),
                  ('Rampe rouge',.10+.60/(1+np.exp(-(k-575)/22))),
                  ('Rampe bleue',.10+.60/(1+np.exp((k-490)/22))),
                  ('Ondulation',.40+.15*np.sin((k-360)*2*np.pi/90)),
                  ('Pic étroit',.18+.50*np.exp(-.5*((k-585)/12)**2))]
        for name,spectrum in variants:names.append(name);spectra.append(spectrum)
        pair,info=self.metamer_pair()
        names.extend(['Métamère A','Métamère B']);spectra.extend(pair)
        spectra=np.array(spectra)
        rgb=self.rgb_from_reflectance(spectra)
        if rgb.min() < -1e-10 or rgb.max()>1+1e-10:
            raise RuntimeError('Une plage de la mire est hors sRGB ; revoir sa définition.')
        return names,spectra,np.clip(rgb,0,1),info
