# File: plom.py
# File Created: Monday, 8th July 2019 10:25:45 am
# Author: Philippe Hawi (hawi@usc.edu)

"""
Tools for learning an intrinsic manifold using Diffusion-Maps, sampling new 
data on the manifold by solving an Ito SDE, and conditioning using 
non-parametric density estimations.
"""

import pickle
import time
from datetime import datetime

import numpy as np
import matplotlib.pyplot as plt
from scipy.spatial import distance_matrix
from joblib import Parallel, delayed


def initialize(training=None,
               
               scaling=True,
               scaling_method='Normalization',
               
               pca=True,
               pca_method='cum_energy',
               pca_cum_energy=1-1e-5,
               pca_eigv_cutoff=0,
               pca_dim=1,
               pca_scale_evecs=True,
               
               dmaps=True,
               dmaps_epsilon='auto',
               dmaps_kappa=1,
               dmaps_L=0.1,
               dmaps_first_evec=False,
               dmaps_m_override=0,
               dmaps_dist_method='standard',
               
               sampling=True,
               projection=True,
               projection_source='pca',
               projection_target='dmaps',
               num_samples=1,
               ito_f0=1,
               ito_dr=0.1,
               ito_steps='auto',
               ito_pot_method=2,
               ito_kde_bw_factor=1,
               parallel=False,
               n_jobs=-1,
               save_samples=True,
               samples_fname=None,
               
               job_desc="Job 1",
               verbose=True
               ):

    inp_params_dict = dict()
    inp_params_dict['pca_cum_energy']        = pca_cum_energy
    inp_params_dict['pca_eigv_cutoff']       = pca_eigv_cutoff
    inp_params_dict['pca_dim']               = pca_dim
    inp_params_dict['dmaps_epsilon']         = dmaps_epsilon
    inp_params_dict['dmaps_kappa']           = dmaps_kappa
    inp_params_dict['dmaps_L']               = dmaps_L
    inp_params_dict['ito_f0']                = ito_f0
    inp_params_dict['ito_dr']                = ito_dr
    inp_params_dict['ito_steps']             = ito_steps
    inp_params_dict['ito_kde_bw_factor']     = ito_kde_bw_factor
    inp_params_dict['ito_num_samples']       = num_samples
    
    options_dict = dict()
    options_dict['scaling']           = scaling
    options_dict['scaling_method']    = scaling_method
    options_dict['pca']               = pca   
    options_dict['pca_method']        = pca_method
    options_dict['pca_scale_evecs']   = pca_scale_evecs
    options_dict['dmaps']             = dmaps
    options_dict['dmap_first_evec']   = dmaps_first_evec
    options_dict['dmaps_m_override']  = dmaps_m_override
    options_dict['dmaps_dist_method'] = dmaps_dist_method
    options_dict['projection']        = projection
    options_dict['sampling']          = sampling
    options_dict['projection_source'] = projection_source
    options_dict['projection_target'] = projection_target
    options_dict['ito_pot_method']    = ito_pot_method
    options_dict['ito_kde_bw_factor'] = ito_kde_bw_factor
    options_dict['parallel']          = parallel
    options_dict['n_jobs']            = n_jobs
    options_dict['save_samples']      = save_samples
    options_dict['samples_fname']     = samples_fname
    options_dict['verbose']           = verbose
    
    scaling_dict = dict()
    scaling_dict['training']         = None
    scaling_dict['centers']          = None
    scaling_dict['scales']           = None
    scaling_dict['reconst_training'] = None
    scaling_dict['augmented']        = None
    
    pca_dict = dict()
    pca_dict['training']         = None
    pca_dict['scaled_evecs_inv'] = None
    pca_dict['scaled_evecs']     = None
    pca_dict['evecs']            = None
    pca_dict['mean']             = None
    pca_dict['eigvals']          = None
    pca_dict['eigvals_trunc']    = None
    pca_dict['reconst_training'] = None
    pca_dict['augmented']        = None
    
    dmaps_dict = dict()
    dmaps_dict['training']      = None
    dmaps_dict['eigenvectors']  = None
    dmaps_dict['eigenvalues']   = None
    dmaps_dict['dimension']     = None
    dmaps_dict['epsilon']       = None
    dmaps_dict['basis']         = None
    dmaps_dict['reduced_basis'] = None
    dmaps_dict['eps_vs_m']      = None
    
    ito_dict = dict()
    ito_dict['Z0']            = None
    ito_dict['a']             = None
    ito_dict['Zs']            = None
    ito_dict['Zs_steps']      = None
    ito_dict['t']             = None
    
    data_dict = dict()
    data_dict['training']         = training
    data_dict['augmented']        = None
    data_dict['reconst_training'] = None
    data_dict['rmse']             = None

    plom_dict = dict()
    plom_dict['job_desc'] = job_desc
    plom_dict['data']     = data_dict
    plom_dict['input']    = inp_params_dict
    plom_dict['options']  = options_dict
    plom_dict['scaling']  = scaling_dict
    plom_dict['pca']      = pca_dict
    plom_dict['dmaps']    = dmaps_dict
    plom_dict['ito']      = ito_dict
    plom_dict['summary']  = None

    return plom_dict
###############################################################################
def parse_input(input_file="input.txt"):
    
    with open(input_file, 'r') as f:
        lines = f.readlines()
    
    lines = [line.lstrip() for line in lines if 
             not line.lstrip().startswith(('*', '#')) and len(line.lstrip())]
    
    lines = [line.split('#')[0].rstrip() for line in lines]
    
    lines = [line.replace("'", "").replace('"', '') for line in lines]
    
    args = dict()
    for line in lines:
        split = line.split()
        key = split[0]
        val = line.replace(key, '', 1).lstrip()
        try:
            val = int(val)
        except:
            try:
                val = float(val)
            except:
                pass
    
        if (val == "True" or val == "true"):
            val = True
        if (val == "False" or val == "false"):
            val = False
        if (val == "None" or val == "none"):
            val = None
        
        if key == "training":
            try:
                val = np.loadtxt(val)
            except:
                try:
                    val = np.load(val)
                except:
                    raise OSError("Training data file not found. File should" +
                                  " be raw text or Numpy array (.npy)")
        
        args[key] = val
    
    return args
    
###############################################################################
def _scaleMinMax(X, verbose=True):
    """
    Scale the features of dataset X.
    
    Data is scaled to be in interval [0, 1]. If any dimensions have zero range
    (constant vector), then set that scale to 1.
    
    Parameters
    ----------
    X : ndarray of shape (n_samples, n_features)
        Input data that will be scaled.
    
    verbose : bool, (default is True)
        If True, print relevant information. The default is True.
    
    Returns
    -------
    X_scaled : ndarray of shape (n_samples, n_features)
        Scaled data.
    
    means : ndarray of shape (n_features, )
        Means of individual features.
    
    scales : ndarray of shape (n_features, )
        Range of individual features.

    """
    if verbose:
        print("\n\nScaling data.")
        print("-------------")
        print("Input data dimensions:", X.shape)
        print("Using 'MinMax' scaler.")

    Xmin = np.min(X, axis=0)
    Xmax = np.max(X, axis=0)
    scale = Xmax - Xmin
    scale[scale==0] = 1
    X_scaled = (X - Xmin) / scale
    if verbose:
        # print("Scaling complete.")
        print("Output data dimensions:", X_scaled.shape)
    return X_scaled, Xmin, scale

###############################################################################
def _scaleNormalize(X, verbose=True):
    """
    Scale the features of dataset X.
    
    Data is scaled to have zero mean and unit variance. If any dimensions have
    zero variance, then set that scale to 1.

    Parameters
    ----------
    X : ndarray of shape (n_samples, n_features)
        Input data that will be scaled.
    
    verbose : bool, optional
        If True, print relevant information. The default is True.

    Returns
    -------
    X_scaled : ndarray of shape (n_samples, n_features)
        Scaled data.
    
    means : ndarray of shape (n_features, )
        Means of individual features.
    
    scales : ndarray of shape (n_features, )
        Standard deviations of individual features.

    """
    if verbose:
        print("\n\nScaling data.")
        print("-------------")
        print("Input data dimensions:", X.shape)
        print("Using 'Normalization' scaler.")
    
    means, scales = np.mean(X, axis=0), np.std(X, axis=0)
    scales[scales == 0.0] = 1.0
    X_scaled = (X - means) / scales
    if verbose:
        # print("Scaling complete.")
        print("Output data dimensions:", X_scaled.shape)
    return X_scaled, means, scales

###############################################################################
def scale(plom_dict):
    """
    PLoM wrapper for scaling functions.

    Parameters
    ----------
    plom_dict : dictionary
        PLoM dictionary containing all elements computed by the PLoM framework.
        The relevant dictionary key gets updated by this function.

    Returns
    -------
    None.

    """
    training       = plom_dict['data']['training']
    scaling_method = plom_dict['options']['scaling_method']
    verbose        = plom_dict['options']['verbose']
    
    if scaling_method == "MinMax":
        scaled_train, centers, scales = _scaleMinMax(training, verbose)
    elif scaling_method == "Normalization":
        scaled_train, centers, scales = _scaleNormalize(training, verbose)
    
    plom_dict['scaling']['training'] = scaled_train
    plom_dict['scaling']['centers']  = centers
    plom_dict['scaling']['scales']   = scales

###############################################################################
def _inverse_scale(X, centers, scales, verbose=True):
    """
    Scale back the data to the original representation.

    Parameters
    ----------
    X : ndarray of shape (n_samples, n_features)
        Data set to be scaled back to original representation.
    
    means : ndarray of shape (n_features, )
        Means of individual features.
    
    scales : ndarray of shape (n_features, )
        Range of individual features.

    Returns
    -------
    X_unscaled : ndarray of shape (n_samples, n_features)
        Unsaled data set.

    """
    return X * scales + centers

###############################################################################
def inverse_scale(plom_dict):
    """
    PLoM wrapper for inverse scaling function.

    Parameters
    ----------
    plom_dict : dictionary
        PLoM dictionary containing all elements computed by the PLoM framework.
        The relevant dictionary key gets updated by this function.

    Returns
    -------
    None.

    """
    centers = plom_dict['scaling']['centers']
    scales  = plom_dict['scaling']['scales']
    
    reconst_training = plom_dict['scaling']['reconst_training']
    augmented        = plom_dict['scaling']['augmented']
    
    if reconst_training is not None:
        X = _inverse_scale(reconst_training, centers, scales)
        plom_dict['data']['reconst_training'] = X
    
    if augmented is not None:
        X = _inverse_scale(augmented, centers, scales)
        plom_dict['data']['augmented'] = X

###############################################################################
def _pca(X, method='cum_energy', cumulative_energy=(1-1e-7), 
         eigenvalues_cutoff=0, pca_dim=1, scale_evecs=True, verbose=True):    
    """
    Normalize data set (n_samples x n_features) via PCA.
    
    Parameters
    ----------
    X: ndarray of shape (n_samples, n_features)
        Input data that will be normalized via PCA.
    
    method : string, optional (default is 'cum_energy')
        Method to select dimension (nu) of truncated basis.
        If 'cum_energy', use 'cumulative_energy' (see below).
        If 'eigv_cutoff', use 'eigenvalues_cutoff' (see below).
        If 'pca_dim', use 'pca_dim' (see below).
    
    cumulative_energy : float, (default is (1-1e-7))
        Used if method = 'cum_energy'.
        Specifies the total cumulative energy needed to truncate the basis. 
        The dimension 'nu' is selected as the smallest integer such that the 
        sum of the largest 'nu' eigenvalues divided by the sum of all 
        eigenvalues is greater than or equal to 'cumulative_energy'.
    
    eigenvalues_cutoff : float, (default is 0)
        Used if method = 'eigv_cutoff'.
        Specifies the smallest eigenvalue for which an eigenvector (basis 
        vector) is retained. Eigenvectors associated with eigenvalues smaller 
        than this cutoff value are dropped.
    
    pca_dim : int, optional (default is 1)
        Used if method = 'pca_dim'.
        Specifies dimension (nu = pca_dim) to be used for the truncated basis.
    
    scale_evecs: bool, optional (default is True)
        If True, the principal components (eigenvectors of the covariance matrix
        of X, onto which X is project) are scaled by the inverse of the square 
        root of the eigenvalues:
        scaled_eigvecs = eigvecs / sqrt_eigvals
    
    verbose : bool, optional (default is True)
        If True, print relevant information.
    
    Returns
    -------
    X_pca : ndarray of shape (n_samples, nu)
        Normalized data.
    
    scaled_eigvecs_inv : ndarray of shape (n_features, nu)
        Eigenvectors scaled by square root of eigenvalues (to be used for 
        denormalization if 'scale_evecs' is True).
    
    scaled_eigvecs: ndarray of shape (n_features, nu)
        Eigenvectors scaled by the inverse of the square root of the 
        eigenvalues. Used for projection of X if 'scale_evecs' is True.
    
    eigvecs: ndarray of shape (n_features, nu)
        Unscaled eigenvectors. Used for projection of X if 'scale_evecs' is 
        False.
    
    means : ndarray of shape (n_features, )
        Means of the individual features.
    
    eigvals : ndarray of shape (nu, )
        Eigenvalues of the covariance matrix of the data set.
    
    eigvals_trunc : ndarray of shape (n_features, )
        Top nu eigenvalues of the covariance matrix of the data set.
    
    """
    if verbose:
        print("\n\nPerforming PCA.")
        print("---------------")
        print("Input data dimensions:", X.shape)
    N, n = X.shape
    means = np.mean(X, axis=0)
    X = X - means
    cov = np.cov(X.T)
    eigvals, eigvecs = np.linalg.eigh(cov)
    if verbose:
        print("PCA eigenvalues:", eigvals)
    
    if method=='eigv_cutoff':
        if verbose:
            print(f"Using specified cutoff value = {eigenvalues_cutoff} "
                  "for truncation.")
            print(f"Dropping eigenvalues less than {eigenvalues_cutoff}")
        eigvals_trunc = eigvals[eigvals > eigenvalues_cutoff]
        if verbose:
            print("PCA retained eigenvalues:", eigvals_trunc)
    elif method=='cum_energy':
        if verbose:
            print("Criteria for truncation: cumulative energy content = "
                  f"{cumulative_energy}")
        tot_eigvals = np.sum(eigvals)
        for i in range(len(eigvals)+1):
            if np.sum(eigvals[0:i])/tot_eigvals > (1-cumulative_energy):
                eigvals_trunc = eigvals[i-1:]
                break
        if verbose:
            print("PCA retained eigenvalues:", eigvals_trunc)
            print("PCA cumulative energy content =",
                  np.sum(eigvals_trunc)/tot_eigvals)
    elif method=='pca_dim':
        if verbose:
            print(f"Using specified PCA dimension = {pca_dim}")
        eigvals_trunc = eigvals[-pca_dim:]
        if verbose:
            print("PCA retained eigenvalues:", eigvals_trunc)

    if verbose:
        print("Number of features:", n, "->", len(eigvals_trunc))
    num_dropped_features = n - len(eigvals_trunc)
    eigvecs = eigvecs[:, num_dropped_features:]
    sqrt_eigvals = np.sqrt(eigvals_trunc)
    scaled_eigvecs = eigvecs / sqrt_eigvals
    scaled_eigvecs_inv = eigvecs * sqrt_eigvals
    
    # compute X_pca as wide matrix (then transpose); faster in later comps
    if scale_evecs:
        X_pca = np.dot(scaled_eigvecs.T, X.T).T
    else:
        X_pca = np.dot(eigvecs.T, X.T).T
    
    # compute X_pca as tall matrix; slower in later comps
    # X_pca = np.dot(X, scaled_eigvecs)
    
    if verbose:
        print("Output data dimensions:", X_pca.shape)
    return (X_pca, scaled_eigvecs_inv, scaled_eigvecs, eigvecs, means, eigvals, 
            eigvals_trunc)

###############################################################################
def pca(plom_dict):
    """
    PLoM wrapper for normalization (PCA) function.

    Parameters
    ----------
    plom_dict : dictionary
        PLoM dictionary containing all elements computed by the PLoM framework.
        The relevant dictionary key gets updated by this function.

    Returns
    -------
    None.

    """
    scaling = plom_dict['options']['scaling']
    if scaling:
        X = plom_dict['scaling']['training']
    else:
        X = plom_dict['data']['training']
    
    method      = plom_dict['options']['pca_method']
    scale_evecs = plom_dict['options']['pca_scale_evecs']
    verbose     = plom_dict['options']['verbose']
    
    cumulative_energy  = plom_dict['input']['pca_cum_energy']
    eigenvalues_cutoff = plom_dict['input']['pca_eigv_cutoff']
    pca_dim            = plom_dict['input']['pca_dim']
    
    (X_pca, scaled_evecs_inv, scaled_evecs, evecs, 
    means, evals, evals_trunc) = _pca(X, method, cumulative_energy, 
                                      eigenvalues_cutoff, pca_dim, scale_evecs,
                                      verbose=verbose)
    
    plom_dict['pca']['training']         = X_pca
    plom_dict['pca']['scaled_evecs_inv'] = scaled_evecs_inv
    plom_dict['pca']['scaled_evecs']     = scaled_evecs
    plom_dict['pca']['evecs']            = evecs
    plom_dict['pca']['mean']             = means
    plom_dict['pca']['eigvals']          = evals
    plom_dict['pca']['eigvals_trunc']    = evals_trunc

###############################################################################
def _inverse_pca(X, eigvecs, means):
    """
    Project data set X from PCA space back to original data space.

    Parameters
    ----------
    X : ndarray of shape (n_samples, nu)
        Data set in PCA space (nu-dimensional) to be projected back to original
        data space (n_features-dimensional).

    eigvecs : ndarray of shape (n_features, nu)
        Eigenvectors (principal components) onto which original data X was 
        projected.
    
    means : ndarray of shape (n_features, )
        Means of the individual features.

    Returns
    -------
    X : ndarray of shape (n_samples, n_features)
        Data set projected back to original n_features-dimensional space.

    """
    X = np.dot(X, eigvecs.T) + means    
    return X

###############################################################################
def inverse_pca(plom_dict):
    """
    PLoM wrapper for inverse normalization (inverse PCA) function.

    Parameters
    ----------
    plom_dict : dictionary
        PLoM dictionary containing all elements computed by the PLoM framework.
        The relevant dictionary key gets updated by this function.

    Returns
    -------
    None.

    """
    scale_evecs = plom_dict['options']['pca_scale_evecs']
    if scale_evecs:
        eigvecs = plom_dict['pca']['scaled_evecs_inv']
    else:
        eigvecs = plom_dict['pca']['evecs']
        
    mean    = plom_dict['pca']['mean']
    
    scaling = plom_dict['options']['scaling']
    
    if plom_dict['pca']['reconst_training'] is not None:
        reconst_training = plom_dict['pca']['reconst_training']
    else:
        reconst_training = plom_dict['pca']['training']
    
    augmented = plom_dict['pca']['augmented']
    
    if reconst_training is not None:
        X = _inverse_pca(reconst_training, eigvecs, mean)
        if scaling:
            plom_dict['scaling']['reconst_training'] = X
        else:
            plom_dict['data']['reconst_training'] = X
    
    if augmented is not None:
        X = _inverse_pca(augmented, eigvecs, mean)
        if scaling:
            plom_dict['scaling']['augmented'] = X
        else:
            plom_dict['data']['augmented'] = X

###############################################################################
def _sample_projection(H, g):
    """
    Reduce normalized data (n_samples x nu) to random matrix [Z] (nu x m) 
    using reduced DMAPS basis (n_samples x m).
    Find Z such that: [H] = [Z] [g]^T
    where: [H]: normalized data (nu x n_samples)
           [Z]: projected sample (nu x m)
           [g]: DMAPS basis (n_samples x m)
    => [Z] = [H] [a] where [a] = [g] ([g]^T [g])^-1

    Parameters
    ----------
    H : ndarray of shape (nu, n_samples)
        Data set in PCA or original space. This matrix is fed into the DMAPS 
        machinery to find a reduced basis [g].
    
    g : ndarray of shape (n_samples, m)
        Reduced DMAPS basis (m eigenvectors).

    Returns
    -------
    Z : ndarray of shape (nu, m)
        Reduced normalized data, random matrix [Z].
    
    a : ndarray of shape (n_samples, m)
        Reduction matrix [a].

    """
    a = np.dot(g, np.linalg.inv(np.dot(np.transpose(g), g)))
    if H.shape[1] != a.shape[0]:
        H = H.T
    Z = np.dot(H, a)
    return Z, a

###############################################################################
def sample_projection(plom_dict):
    """
    PLoM wrapper for sample projection ([H] = [Z] [g]^T) function.
    Find [Z] for a given [H].

    Parameters
    ----------
    plom_dict : dictionary
        PLoM dictionary containing all elements computed by the PLoM framework.
        The relevant dictionary key gets updated by this function.

    Returns
    -------
    None.

    """    
    projection_source = plom_dict['options']['projection_source']
    projection_target = plom_dict['options']['projection_target']
    verbose = plom_dict['options']['verbose']
    
    if projection_source == "pca":
        H = plom_dict['pca']['training']
    elif projection_source == "scaling":
        H = plom_dict['scaling']['training']
    else:
        H = plom_dict['data']['training']
    
    if projection_target == "dmaps":
        g = plom_dict['dmaps']['reduced_basis']
    elif projection_target == "pca":
        g = plom_dict['pca']['training']
    
    if H is None:
        if verbose:
            print("Projection source [H] not found. Skipping projection.")
    elif g is None:
        if verbose:
            print("Projection target [g] not found. Skipping projection.")
    else:
        Z0, a = _sample_projection(H, g)
        
        plom_dict['ito']['Z0'] = Z0
        plom_dict['ito']['a']  = a
    
###############################################################################
def _inverse_sample_projection(Z, g):
    """
    Reverse the sample projection procedure.
    Map a random matrix [Z] back to the original space using the DMAPS reduced 
    basis.
    Return new matrix [H] = [Z] [g]^T

    Parameters
    ----------
    Z : ndarray of shape (nu, m)
        Reduced normalized data, random matrix [Z].
    
    g : ndarray of shape (n_samples, m)
        Reduced DMAPS basis (m eigenvectors).

    Returns
    -------
    H : ndarray of shape (n_samples, nu)
        Data set in PCA or original space. This matrix is fed into the DMAPS 
        machinery to find a reduced basis [g]. In case of new projected sample 
        [Z], [H] is a new sample in PCA or original space.
        
    """
    # The following line leads to slower computations later on.
    # H = np.dot(Z, reduced_basis.T).T
    # This is faster.
    H = np.dot(g, Z.T)
    return H

###############################################################################
def inverse_sample_projection(plom_dict):
    """
    PLoM wrapper for inverse sample projection ([H] = [Z] [g]^T) function.
    Find [H] for a given [Z].

    Parameters
    ----------
    plom_dict : dictionary
        PLoM dictionary containing all elements computed by the PLoM framework.
        The relevant dictionary key gets updated by this function.

    Returns
    -------
    None.

    """ 
    projection_source = plom_dict['options']['projection_source']
    projection_target = plom_dict['options']['projection_target']
    
    if projection_target == "dmaps":
        g = plom_dict['dmaps']['reduced_basis']
    elif projection_target == "pca":
        g = plom_dict['pca']['training']
    
    if g is None:
        return
    
    Zs = plom_dict['ito']['Zs']
    X_augmented = None
    if Zs is not None:
        X_augmented = []
        for Z_final in Zs:
            X_augmented.append(_inverse_sample_projection(Z_final, g))
        X_augmented = np.vstack(X_augmented)
    
    Z0 = plom_dict['ito']['Z0']
    X_reconst = _inverse_sample_projection(Z0, g)
    
    if projection_source == "pca":
        plom_dict['pca']['augmented'] = X_augmented
        plom_dict['pca']['reconst_training'] = X_reconst
    elif projection_source == "scaling":
        plom_dict['scaling']['augmented'] = X_augmented
        plom_dict['scaling']['reconst_training'] = X_reconst
    else:
        plom_dict['data']['augmented'] = X_augmented
        plom_dict['data']['reconst_training'] = X_reconst
        
###############################################################################
def _get_dmaps_basis(H, epsilon, kappa=1, diffusion_dist_method='standard'):
    """
    Return DMAPS basis.
    Construct diffusion-maps basis, [g], using specified kernel width, epsilon.

    Parameters
    ----------
    H : ndarray of shape (n_samples, nu)
        Normalized data set for which DMAPS basis is constructed.
    
    epsilon : float
        Diffusion-maps kernel width (smoothing parameter, > 0).
    
    kappa : int, optional (default is 1)
        Related to the analysis scale of the local geometric structure of the 
        dataset.
    
    diffusion_dist_method : string, optional (default is 'standard')
        Experimental. Always use 'standard'.
        If 'standard', compute pair-wise distances using standard L2 norm.
        If 'periodic', compute pair-wise distances using periodic norm.

    Returns
    -------
    basis : ndarray of shape (n_samples, n_samples)
        Diffusion-maps basis, [g].
    
    values : ndarray of shape (n_samples, )
        Diffusion-maps eigenvalues.
    
    vectors : ndarray of shape (n_samples, n_samples)
        Diffusion-maps eigenvectors.

    """    
    if diffusion_dist_method == 'standard':
        distances = np.array([np.sum(np.abs(H - a)**2, axis=1) for a in H])

    elif diffusion_dist_method == 'periodic':
        sh = np.shape(H)
        max_th_val = np.max(H[:,0])
        if sh[1] == 2:
            z_dist = distance_matrix(H[:,1].reshape(sh[0],1), 
                                     H[:,1].reshape(sh[0],1))
        else:
            z_dist = 0
        th_dist = distance_matrix(H[:,0].reshape(sh[0],1), 
                                  H[:,0].reshape(sh[0],1))
        th_dist = np.mod(th_dist+max_th_val,2.0*
                         max_th_val+(2.0*max_th_val/99.0))-max_th_val
        # th_dist[th_dist>(max_th_val)] = (2*max_th_val - 
                                         # th_dist[th_dist>(max_th_val)])
        distances = z_dist**2 + th_dist**2

    diffusions = np.exp(-distances / (epsilon))
    scales = np.sum(diffusions, axis=0)**.5
    P = np.linalg.inv(np.diag(scales**2)).dot(diffusions)
    
    # Note: eigenvectors of transition matrix are the same for any power kappa
    normalized = diffusions / (scales[:, None] * scales[None, :])
    values, vectors = np.linalg.eigh(normalized)
    # values, vectors = np.linalg.eigh(
        # np.linalg.matrix_power(normalized, kappa))
    basis_vectors = vectors / scales[:, None]
    basis = basis_vectors * values[None, :]**kappa
    return np.flip(basis,axis=1), np.flip(values), np.flip(vectors,axis=1)

###############################################################################
def _get_dmaps_optimal_dimension(eigvalues, L):
    """
    Estimate reduced manifold dimension, m, using a scale separation cutoff for
    determining where to truncate the spectral decomposition based on the 
    (sorted-decreasing eigenvalues), i.e., if eigenvalue j+1 is less than 
    eigenvalue 2 by more than this factor, then truncate and use eigenvalues 2 
    through j.
    
    Parameters
    ----------
    eigvals :ndarray of shape (n_samples, )
        DMAPS eigenvalues.
    
    L : float
        DMAPS eigenvalues scale separation cutoff value.
    
    Returns
    -------
    m : int
        Manifold dimension, m.
    
    """
    m = len(eigvalues) - 1
    for a in range(2, len(eigvalues)):
        r = eigvalues[a] / eigvalues[1]
        if r < L:
            m = a - 1
            break
    return m

###############################################################################
def _get_dmaps_dim_from_epsilon(H, epsilon, kappa, L, dist_method='standard'):
    """
    Return manifold dimension, m, given epsilon.
    For the given epsilon, compute the DMAPS basis and eigenvalues, and choose 
    the manifold dimension based on these eigenvalues (with cutoff criteria L).

    Parameters
    ----------
    H : ndarray of shape (n_samples, nu)
        Normalized data set.
    
    epsilon : float
        Diffusion-maps kernel width (smoothing parameter, > 0).
    
    kappa : int, optional (default is 1)
        Related to the analysis scale of the local geometric structure of the 
        dataset.
    
    L : float
        DMAPS eigenvalues scale separation cutoff value.
    
    dist_method : string, optional (default is 'standard')
        Experimental. Always use 'standard'.
        If 'standard', compute pair-wise distances using standard L2 norm.
        If 'periodic', compute pair-wise distances using periodic norm.

    Returns
    -------
    m : int
        Manifold dimension.

    """
    basis, eigvals, eigvecs = _get_dmaps_basis(H, epsilon, kappa, dist_method)
    m = _get_dmaps_optimal_dimension(eigvals, L)
    return m

###############################################################################
def _get_dmaps_optimal_epsilon(H, kappa, L, dist_method='standard'):
    """
    Used when epsilon is not specified by user (epsilon='auto').
    Estimate optimal DMAPS kernel width, epsilon.
    Criteria for estimation: choose smallest epsilon that results in smallest 
    manifold dimension, m.
    After estimating epsilon, construct DMAPS basis [g] for  estimated epsilon
    and return epsilon, DMAPS basis, DMAPS eigenvalues, and manifold dimension.

    Parameters
    ----------
    H : ndarray of shape (n_samples, nu)
        Normalized data.
    
    kappa : int
        Related to the analysis scale of the local geometric structure of the 
        dataset.
    
    L : float
        DMAPS eigenvalues scale separation cutoff value.
    
    dist_method : string, optional (default is 'standard')
        Experimental. Always use 'standard'.
        If 'standard', compute pair-wise distances using standard L2 norm.
        If 'periodic', compute pair-wise distances using periodic norm.

    Returns
    -------
    epsilon : float
        Optimal epsilon. This is the smallest epsilon that results in the 
        smallest manifold dimension satisfying the DMAPS eigenvalue cutoff 
        criteria (L).
    
    m_target : int
        Target manifold dimension. This is usally the smallest possible 
        dimension satisfying the DMAPS eigenvalue cutoff criteria (L).
    
    eps_vs_m : ndarray of shape (?, 2)
        Matrix of Epsilon (1st column) vs manifold dimension (2nd column) used 
        when finding optimal epsilon.

    """
    epsilon_list = [0.1, 1, 2, 8, 16, 32, 64, 100, 10000]
    eps_for_m_target = [1, 10, 100, 1000, 10000]
    eps_vs_m = []
    m_target_list = [_get_dmaps_dim_from_epsilon(H, eps, kappa, L, 
                                                 dist_method) 
                     for eps in eps_for_m_target]
    m_target = min(m_target_list)
    upper_bound = eps_for_m_target[np.argmin(m_target_list)]
    lower_bound = epsilon_list[0]
    for eps in epsilon_list[1:]:
        m = _get_dmaps_dim_from_epsilon(H, eps, kappa, L)
        eps_vs_m.append([eps, m])
        if m > m_target:
            lower_bound = eps
        else:
            upper_bound = eps
            break
    while upper_bound - lower_bound > 0.5:
        middle_bound = (lower_bound+upper_bound)/2
        m = _get_dmaps_dim_from_epsilon(H, middle_bound, kappa, L)
        eps_vs_m.append([middle_bound, m])
        if m > m_target:
            lower_bound = middle_bound
        else:
            upper_bound = middle_bound
    m = _get_dmaps_dim_from_epsilon(H, lower_bound, kappa, L)
    while m > m_target:
        lower_bound += 0.1
        m = _get_dmaps_dim_from_epsilon(H, lower_bound, kappa, L)
        eps_vs_m.append([lower_bound, m])
    epsilon = lower_bound
    eps_vs_m = np.unique(eps_vs_m, axis=0)
    return epsilon, m_target, eps_vs_m

###############################################################################
def _dmaps(X, epsilon, kappa=1, L=0.1, first_evec=False, m_override=0,
           dist_method='standard', verbose=True):
    """
    Perform Diffusion-maps analysis on input data set.
    Given data set X, this function performs DMAPS on X using either an 
    optimal value of the DMAPS kernel bandwidth or a specified value.
    This function returns the DMAPS full basis, truncated basis, eigenvalues, 
    manifold dimension, and the epsilon used for the analysis.

    Parameters
    ----------
    X : ndarray of shape (n_samples, nu)
        Data set on which DMAPS analysis is performed. This is usually the 
        normalized data set (PCA).
    
    epsilon : float
        Diffusion-maps kernel width (smoothing parameter, > 0).
    
    kappa : int, optional (default is 1)
        Related to the analysis scale of the local geometric structure of the 
        dataset.
    
    L : float, optional (default is 0.1)
        DMAPS eigenvalues scale separation cutoff value.
    
    first_evec : bool, optional (default is False)
        If True, the first DMAPS eigenvector (constant, usally dropped) is 
        included in the DMAPS reduced basis.
    
    m_override : int, optional (default is 0)
        If greater than 0, this overrides the calculated dimension of the 
        manifold, and sets the dimension equal to 'm_override'.
    
    dist_method : string, optional (default is 'standard')
        Experimental. Always use 'standard'.
        If 'standard', compute pair-wise distances using standard L2 norm.
        If 'periodic', compute pair-wise distances using periodic norm.
    
    verbose : bool, optional (default is True)
        If True, print relevant information.

    Returns
    -------
    red_basis : ndarray of shape (n_samples, m)
        Reduced DMAPS basis (m eigenvectors).
        
    basis : ndarray of shape (n_samples, n_samples)
        Full DMAPS basis (n_samples eigenvectors).
        
    epsilon : float
        Diffusion-maps kernel width (specified or computed as optimal value) 
        used when computing the DMAPS basis.
        
    m : int
        Reduced DMAPS basis dimension
        
    eigvals : ndarray of shape (n_samples, )
        DMAPS eigenvalues.
        
    eigvecs : ndarray of shape (n_samples, n_samples)
        DMAPS eigenvectors.
        
        
    eps_vs_m : ndarray of shape (?, 2)
        Matrix of Epsilon (1st column) vs manifold dimension (2nd column) used 
        when finding optimal epsilon.
    
    """
    start_time = datetime.now()
    if verbose:
        print("\n\nPerforming DMAPS analysis.")
        print("--------------------------")
        print("Input data dimensions:", X.shape)

    if epsilon == 'auto':
        if verbose:
            print("Finding best epsilon for analysis.")
        epsilon, m_opt, eps_vs_m = _get_dmaps_optimal_epsilon(X, kappa, L, 
                                                              dist_method)
        basis, eigvals, eigvecs = _get_dmaps_basis(X, epsilon, kappa, 
                                                   dist_method)
        if m_override > 0:
            m = m_override
        else:
            m = m_opt
        if verbose:
            print("Epsilon = %.2f" %epsilon)
            print(f"Manifold eigenvalues: {str(eigvals[1:m+2])[1:-1]} [...]")
            print(f"Manifold dimension: m optimal = {m_opt}")
            if m_override>0:
                print("Overriding manifold dimension.")
            print(f"m used = {m}")
    
    else:
        eps_vs_m = []
        epsilon = np.atleast_1d(epsilon)
        if len(epsilon)==1 and verbose:
            print("Using specified epsilon for analysis.")
        elif verbose:
            print("Using specified epsilon list for analysis.")
        for eps in epsilon:
            basis, eigvals, eigvecs = _get_dmaps_basis(X, eps, kappa, 
                                                       dist_method)
            m_opt = _get_dmaps_optimal_dimension(eigvals, L)
            if m_override > 0:
                m = m_override
            else:
                m = m_opt
            eps_vs_m.append([eps, m_opt])
            if verbose:
                if len(epsilon)>1:
                    print("++++++++++++++++++++++++++++++++++++++++++++++++++")
                print("Epsilon = %.2f" %eps)
                print(f"Manifold eigenvalues: {str(eigvals[1:m+2])[1:-1]} "
                      "[...]")
                print(f"Manifold dimension: m optimal = {m_opt}")
                if m_override>0:
                    print("Overriding manifold dimension.")
                print(f"m used = {m}")
        if verbose:
            if len(epsilon)>1:
                print("++++++++++++++++++++++++++++++++++++++++++++++++++")
                print("++++++++++++++++++++++++++++++++++++++++++++++++++")
                print("Using last epsilon in specified list.")
                print("Epsilon = %.2f" %eps)
                print(f"Manifold eigenvalues: {str(eigvals[1:m+2])[1:-1]} " 
                      "[...]")
                print(f"Manifold dimension: m optimal = {m_opt}")
                if m_override>0:
                    print("Overriding manifold dimension.")
                print(f"m used = {m}")
        epsilon =  epsilon[-1]
        eps_vs_m = np.unique(eps_vs_m, axis=0)

        
    if first_evec: # indices of first and last eigenvectors to be used
        if verbose:
            print("Including first (trivial) eigenvector in projection basis.")
        s = 0
        if m_override==0:
            m = m+1
        e = m
    else:
        s = 1
        e = m+1
    red_basis = basis[:, s:e]
    
    # eps_vs_m.sort() # not needed since np.unique is used a few lines earlier
    
    end_time = datetime.now()
    if verbose:
        print(f'Using {e-s} DMAPS eigenvectors ({s} to {e-1}).')
        print(f"DMAPS data dimensions: {red_basis.shape}")
        print(f"*** DMAPS time = {str(end_time-start_time)[:-3]} ***")
    return red_basis, basis, epsilon, m, eigvals, eigvecs, eps_vs_m

###############################################################################
def dmaps(plom_dict):
    """
    PLoM wrapper for dmaps function.

    Parameters
    ----------
    plom_dict : dictionary
        PLoM dictionary containing all elements computed by the PLoM framework.
        The relevant dictionary key gets updated by this function.

    Returns
    -------
    None.

    """
    
    epsilon = plom_dict['input']['dmaps_epsilon']
    kappa   = plom_dict['input']['dmaps_kappa']
    L       = plom_dict['input']['dmaps_L']
    first_evec  = plom_dict['options']['dmap_first_evec']
    m_override  = plom_dict['options']['dmaps_m_override']
    dist_method = plom_dict['options']['dmaps_dist_method']
    verbose     = plom_dict['options']['verbose']
    
    if plom_dict['pca']['training'] is not None:
        X = plom_dict['pca']['training']
    elif plom_dict['scaling']['training'] is not None:
        X = plom_dict['scaling']['training']
    else:
        X = plom_dict['data']['training']
    
    red_basis, basis, epsilon, m, eigvals, eigvecs, eps_vs_m = \
        _dmaps(X, epsilon, kappa, L, first_evec, m_override, dist_method, 
               verbose)
    
    plom_dict['dmaps']['eigenvectors']  = eigvecs
    plom_dict['dmaps']['eigenvalues']   = eigvals
    plom_dict['dmaps']['dimension']     = m
    plom_dict['dmaps']['epsilon']       = epsilon
    plom_dict['dmaps']['basis']         = basis
    plom_dict['dmaps']['reduced_basis'] = red_basis
    plom_dict['dmaps']['training']      = red_basis
    plom_dict['dmaps']['eps_vs_m']      = eps_vs_m

###############################################################################
def _get_L(H, u, kde_bw_factor=1, method=2):
    """
    Compute the gradient of the potential to be used in each ito step.
    
    Parameters
    ----------
    H : ndarray of shape (nu, n_samples)
        Typically, this is the normalized (PCA) data set. If the 
        non-normalized data set is used, this would be of shape 
        (n_features, n_samples).
        
    u :  ndarray of shape (nu, n_samples) 
        Product of intermediate matrix [zHalf] and transpose of reduced DMAPS 
        basis [g].
    
    kde_bw_factor : float, optional (default is 1.0)
        Multiplier that modifies the computed KDE bandwidth (Silverman 
        rule-of-thumb).
    
    method : int, optional (default is 2)
        Experimental.
        This is the most expensive part of the computation. 
        Methods 1-8 compute the same joint KDE using different algorithms.
        Method 2 is the most efficient.
        Method 9 computes a conditional (Nadaraya-Watson KDE) * marginal tanh 
        approximation. This is used when the distribution of one of the 
        variables is to be specified.
        Method 10 a computes conditional (Nadaraya-Watson KDE) * marginal KDE.
            
    Returns
    -------
    pot : ndarray of shape (nu, n_samples)
        Gradient of the potential for the given u. 
    
    """
    if method==1: # joint KDE
        nu, N = H.shape
        s = (4 / (N*(2+nu))) ** (1/(nu+4))*kde_bw_factor
        shat = s / np.sqrt(s**2 + (N-1)/N)
        scaled_H = H * shat / s
        
        dist_mat_list = list(map(lambda x: (scaled_H.T - x).T, u.T))
        
        norms_list = np.exp((-1/(2*shat**2)) * np.array(list(map(\
            lambda x: np.linalg.norm(x, axis=0)**2, dist_mat_list))))
        
        q_list = np.array(list(map(np.sum, norms_list))) / N
        
        product = np.array(list(map(np.dot, dist_mat_list, norms_list)))
        
        dq_list = product/shat**2/N
        pot = (dq_list/q_list[:,None]).transpose()
    
    elif method==2: # joint KDE
        nu, N = H.shape
        s = (4 / (N*(2+nu))) ** (1/(nu+4))*kde_bw_factor
        shat = s / np.sqrt(s**2 + (N-1)/N)
        scaled_H = H * shat / s
        
        dist_mat_list = [(scaled_H.T - x).T for x in u.T]
        
        norms_list = np.exp((-1/(2*shat**2)) * np.array(list(map(\
            lambda x: np.linalg.norm(x, axis=0)**2, dist_mat_list))))
        
        q_list = np.array(list(map(np.sum, norms_list))) / N
        
        product = np.array(list(map(np.dot, dist_mat_list, norms_list)))
        
        dq_list = product/shat**2/N
        pot = (dq_list/q_list[:,None]).transpose()
    
    elif method==3: # joint KDE
        nu, N = H.shape
        s = (4 / (N*(2+nu))) ** (1/(nu+4))*kde_bw_factor
        shat = s / np.sqrt(s**2 + (N-1)/N)
        scaled_H = H * shat / s
        
        dist_mat_list = np.asfortranarray(np.tile(scaled_H.T, (N, 1)) - 
                        np.repeat(u.T, N, axis=0))
        norms_list = np.exp((-1/(2*shat**2)) * 
                     np.linalg.norm(dist_mat_list, axis=1)**2)
        q_list = np.sum(np.reshape(norms_list, (N, N)), axis=1) / N
        product = dist_mat_list * norms_list[:, None] / shat**2 / N
        dq_list = np.sum(np.reshape(product, (N, N, -1)), axis=1)
        pot = (dq_list / q_list[:,None]).T
    
    
    
    elif method==4:    
        nu, N = H.shape
        s = (4 / (N*(2+nu))) ** (1/(nu+4))*kde_bw_factor
        shat = s / np.sqrt(s**2 + (N-1)/N)
        scaled_H = H * shat / s

        dist_mat_list = list(map(lambda x: (scaled_H.T - x).T, u.T))
        
        norms_list = np.exp((-1/(2*shat**2)) * \
            (distance_matrix(scaled_H.T, u.T)**2).T) # N x N
        
        q_list = np.array(list(map(np.sum, norms_list))) / N
        
        product = np.array(list(map(np.dot, dist_mat_list, norms_list)))
        
        dq_list = product/shat**2/N
        pot = (dq_list/q_list[:,None]).transpose()
    
    elif method==5:    
        nu, N = H.shape
        s = (4 / (N*(2+nu))) ** (1/(nu+4))*kde_bw_factor
        shat = s / np.sqrt(s**2 + (N-1)/N)
        scaled_H = H * shat / s

        dist_mat_list = [(scaled_H.T - x).T for x in u.T]
        
        norms_list = np.exp((-1/(2*shat**2)) * \
            (distance_matrix(scaled_H.T, u.T)**2).T) # N x N
        
        q_list = np.array(list(map(np.sum, norms_list))) / N
        
        product = np.array(list(map(np.dot, dist_mat_list, norms_list)))
        
        dq_list = product/shat**2/N
        pot = (dq_list/q_list[:,None]).transpose()
    
    elif method==6:    
        nu, N = H.shape
        s = (4 / (N*(2+nu))) ** (1/(nu+4))*kde_bw_factor
        shat = s / np.sqrt(s**2 + (N-1)/N)
        scaled_H = H * shat / s

        dist_mat_list = list(map(lambda x: (scaled_H.T - x).T, u.T))
        
        norms_list = np.exp(
            (-1/(2*shat**2)) * 
            np.array([np.linalg.norm(x, axis=0)**2 for x in dist_mat_list]))
        
        q_list = np.array(list(map(np.sum, norms_list))) / N
        
        product = np.array(list(map(np.dot, dist_mat_list, norms_list)))
        
        dq_list = product/shat**2/N
        pot = (dq_list/q_list[:,None]).transpose()
    
    elif method==7:    
        nu, N = H.shape
        s = (4 / (N*(2+nu))) ** (1/(nu+4))*kde_bw_factor
        shat = s / np.sqrt(s**2 + (N-1)/N)
        scaled_H = H * shat / s

        dist_mat_list = [(scaled_H.T - x).T for x in u.T]
        
        norms_list = np.exp(
            (-1/(2*shat**2)) * 
            np.array([np.linalg.norm(x, axis=0)**2 for x in dist_mat_list]))
        
        q_list = np.array(list(map(np.sum, norms_list))) / N
        
        product = np.array(list(map(np.dot, dist_mat_list, norms_list)))
        
        dq_list = product/shat**2/N
        pot = (dq_list/q_list[:,None]).transpose()
            
    elif method==8:
        nu, N = H.shape
        s = (4 / (N*(2+nu))) ** (1/(nu+4))*kde_bw_factor
        shat = s / np.sqrt(s**2 + (N-1)/N)
        scaled_H = H * shat / s
        
        raw_dist = np.array([scaled_H.T - x for x in u.T])

        exp_dist = np.exp((-1/(2*shat**2))*np.sum(raw_dist**2, axis=2))

        q = 1/N * np.sum(exp_dist, axis=1)

        dq = np.array([np.sum(raw_dist[:,:,i]*exp_dist, axis=1) 
                        for i in range(nu)]) / shat**2 / N
        pot = dq/q

    elif method==9:
        nu, N = H.shape
        s = (4 / (N*(2+nu))) ** (1/(nu+4))*kde_bw_factor
        shat = s / np.sqrt(s**2 + (N-1)/N)
        scaled_H = H * shat / s
        
        raw_dist = [scaled_H.T - x for x in u.T]

        exp_dist = np.exp((-1/(2*shat**2))*np.linalg.norm(raw_dist, axis=2)**2)

        q = 1/N * np.sum(exp_dist, axis=1)

        dq = [np.sum(np.array(raw_dist)[:,:,i]*exp_dist, axis=1) 
                        for i in range(nu)]/shat**2/N
        pot = dq/q
    
    elif method==10: # conditional (Nadaraya-Watson KDE) * marginal tanh approx.
        H = H.T
        u = u.T
        nu, N = 1, H.shape[0]
        eta_th = H[:,0]
        eta_z = H[:,1]
        u_th = u[:,0]
        u_z = u[:,1]
        hz = (4 / (N*(2+nu))) ** (1/(nu+4)) * kde_bw_factor
        ht = (4 / (N*(2+nu))) ** (1/(nu+4)) * kde_bw_factor
        a = min(eta_th)
        b = max(eta_th)
        dd = 100
        
        th_raw_dist = np.subtract.outer(u_th, eta_th)
        # numerator of w_i (each row in the matrix corresponds to one theta_l)
        th_dist = np.exp((-1/(2*ht**2)) * (th_raw_dist**2))
        # denom. of w_i (each number in the list corresponds to one theta_l)
        th_dist_tot = np.array(list(map(np.sum,th_dist)))
        q_th = (1/2/(b-a)) * (np.tanh(dd*(u_th-a)) - 
                              np.tanh(dd*(u_th-b))).reshape(N) # q(theta) (N,)
        
        z_raw_dist = np.subtract.outer(u_z, eta_z)
        z_dist = np.exp((-1/(2*hz**2)) * (z_raw_dist**2))
        q_z = np.sum((1/np.sqrt(2*np.pi)/hz * z_dist * th_dist),
                      axis=1) / th_dist_tot # q(z|theta) (N,)
    
        q = q_z * q_th
        
        dq_dz = np.sum((-1/np.sqrt(2*np.pi)/hz**3) * z_raw_dist * z_dist * 
                        th_dist, axis=1) / th_dist_tot * q_th
        
        dq_dt_1 = q_th
        dq_dt_2 = q_z
        dq_dt_3 = (dd/2/(b-a) / (np.cosh(dd*(u_th-a))**2) - 
                    dd/2/(b-a) / (np.cosh(dd*(u_th-b))**2))
        dq_dt_4 = (-1/np.sqrt(2*np.pi)/hz/ht**2 * 
                    np.sum(z_dist * th_raw_dist * th_dist, axis=1) * 
                    th_dist_tot - 
                    (1/np.sqrt(2*np.pi)/hz) * np.sum(z_dist*th_dist, axis=1) * 
                    (-1/ht**2)*np.sum(th_raw_dist*th_dist, axis=1)
                    ) / th_dist_tot**2
        dq_dt = dq_dt_4 * dq_dt_1 + dq_dt_2 * dq_dt_3    
       
        dq = np.array((dq_dt, dq_dz))
        pot = dq/(q)

    elif method==11: # conditional (Nadaraya-Watson KDE) * marginal KDE
        H = H.T
        u = u.T
        nu, N = 1, H.shape[0]
        eta_th = H[:,0]
        eta_z = H[:,1]
        u_th = u[:,0]
        u_z = u[:,1]
        hz = (4 / (N*(2+nu))) ** (1/(nu+4)) * kde_bw_factor
        ht = (4 / (N*(2+nu))) ** (1/(nu+4)) * kde_bw_factor
        
        th_raw_dist = np.subtract.outer(u_th, eta_th)
        # numerator of w_i (each row in the matrix corresponds to one theta_l)
        th_dist = np.exp((-1/(2*ht**2)) * (th_raw_dist**2))
        # denom. of w_i (each number in the list corresponds to one theta_l)
        th_dist_tot = np.array(list(map(np.sum,th_dist)))
        # q(theta) (N,)
        q_th = (1/N/ht) * np.sum((1/np.sqrt(2*np.pi) * th_dist), axis=1)
        
        z_raw_dist = np.subtract.outer(u_z, eta_z)
        z_dist = np.exp((-1/(2*hz**2)) * (z_raw_dist**2))
        # q(z|theta) (N,)
        q_z  = np.sum((1/np.sqrt(2*np.pi)/hz * z_dist * th_dist), 
                      axis=1) / th_dist_tot
    
        q = q_z * q_th
        
        dq_dz = np.sum((-1/np.sqrt(2*np.pi)/hz**3) * z_raw_dist * z_dist * 
                        th_dist, axis=1) / th_dist_tot * q_th
        
        dq_dt_1 = q_th
        dq_dt_2 = q_z
        dq_dt_3 = np.sum((-1/np.sqrt(2*np.pi)/ht**3/N) * th_raw_dist * th_dist,
                          axis=1)
        dq_dt_4 = (-1/np.sqrt(2*np.pi)/hz/ht**2 * 
                    np.sum(z_dist * th_raw_dist * th_dist, axis=1) * 
                    th_dist_tot - (1/np.sqrt(2*np.pi)/hz) * 
                    np.sum(z_dist*th_dist, axis=1) * (-1/ht**2) * 
                    np.sum(th_raw_dist*th_dist, axis=1)
                    ) / th_dist_tot**2
        dq_dt = dq_dt_4 * dq_dt_1 + dq_dt_2 * dq_dt_3    
        
        dq = np.array((dq_dt, dq_dz))
        pot = dq/(q)
        
    return pot

###############################################################################
def _simulate_entire_ito(Z, H, basis, a, f0=1, dr=0.1, t='auto', n=1, 
                         parallel=False, n_jobs=-1, kde_bw_factor=1, 
                         pot_method=2, verbose=True):
    """
    Evolve the ISDE for 't' steps 'n' times. Obtain 'n' new samples at the end.
    If t is 'auto', compute required number of steps.
    
    Parameters
    ----------
    Z : ndarray of shape (nu, m)
        Reduced random matrix [Z] before evolution of ISDE.

    H : ndarray of shape (nu, n_samples)
        Typically, this is the normalized (PCA) data set. If the 
        non-normalized data set is used, this would be of shape 
        (n_features, n_samples).

    basis : ndarray of shape (n_samples, m)
        Reduced DMAPS basis.

    a : ndarray of shape (n_samples, m)
        Reduction matrix [a].

    f0 : float, optional (default is 1.0)
        Parameter that allows the dissipation term of the nonlinear 
        second-order dynamical system (dissipative Hamiltonian system) to be 
        controlled (damping that kills the transient response).

    dr : float, optional (default is 0.1)
        Sampling step of the continuous index parameter used in the 
        integration scheme.

    t : int/str, optional (default is 'auto')
        Number of steps that the Ito stochastic differential equation is 
        evolved for.
        If 'auto', number of steps is calculated internally.

    n : int, optional (default is 1)
        Number of times that we sample the manifold. The actual number of 
        data points generated is equal to this 'n' times the original number 
        of points in the data set (n_samples).
    
    parallel : bool, optional (default is False)
        If True, run sampling in parallel.
    
    n_jobs : int, optional (default is -1)
        Number of jobs started by joblib.Parallel().
        Used if 'parallel' is True.
    
    kde_bw_factor : float, optional (default is 1.0)
        Multiplier that modifies the computed KDE bandwidth (Silverman 
        rule-of-thumb).
    
    pot_method : int, optional (default is 2)
        Experimental.
        This is the most expensive part of the computation. 
        Methods 1-8 compute the same joint KDE using different algorithms.
        Method 2 is the most efficient.
        Method 9 computes a conditional (Nadaraya-Watson KDE) * marginal tanh 
        approximation. This is used when the distribution of one of the 
        variables is to be specified.
        Method 10 a computes conditional (Nadaraya-Watson KDE) * marginal KDE.
    
    verbose : bool, optional (default is True)
        If True, print relevant information.
                
    Returns
    -------
    Zs : list of n ndarrays of shape (nu, m) each
         New reduced manifold samples matrix [Zs].
    
    Zs_steps : list n lists of t ndarrays of shape (nu, m)
        Ito steps for generated samples. FOR DEBUGGING.
    
    t : int
        Number of steps used in the Ito stochastic differential equation 
        evolution.
    
    """
    st = datetime.now()
    nu, N = H.shape
    s = (4 / (N*(2+nu))) ** (1/(nu+4)) * kde_bw_factor
    shat = s / np.sqrt(s**2 + (N-1)/N)
    fac = 2.0*np.pi*shat / dr
    if verbose: 
        print(f"From Ito sampler: fac = {fac:.3f}")
    steps = 4*np.log(100)/f0/dr
    if t == 'auto':
        t = int(steps+1)
    if verbose: 
        print(f"From Ito sampler: {steps:.1f} steps needed; {t:.0f} steps ", 
              "provided")
    Zs = []
    Zs_steps = []
    if parallel:
        if verbose:
            print(f'Generating {n} samples in parallel...')
        res = Parallel(n_jobs=n_jobs)(
            delayed(_simulate_ito_walk)(
                Z, t, H, basis, a, f0, dr, kde_bw_factor, pot_method) 
            for i in range(n))
        [Zs, Zs_steps] = np.array(res, dtype=object).T
    else:
        for i in range(n):
            Zw, Z_steps = _simulate_ito_walk(Z,  t, H, basis, a, f0, dr, 
                                             kde_bw_factor, pot_method)
            if verbose:
                print("Sample %i/%i generated." %((i+1),n))
            Zs.append(Zw)
            Zs_steps.append(Z_steps)
    et = datetime.now()
    if verbose:
        print(f"*** Sampling time = {str(et-st)[:-3]} ***")
    return Zs, Zs_steps, t

###############################################################################
def _simulate_ito_walk(Z, t, H, basis, a, f0=1, dr=0.1, kde_bw_factor=1, 
                       pot_method=2):
    """
    Evolve one ISDE for 't' steps. Obtain one new sample at the end.

    Parameters
    ----------
    Z : ndarray of shape (nu, m)
        Reduced random matrix [Z] before evolution of ISDE.

    t : int
        Number of steps used in the Ito stochastic differential equation 
        evolution.

    H : ndarray of shape (nu, n_samples)
        Typically, this is the normalized (PCA) data set. If the 
        non-normalized data set is used, this would be of shape 
        (n_features, n_samples).

    basis : ndarray of shape (n_samples, m)
        Reduced DMAPS basis.

    a : ndarray of shape (n_samples, m)
        Reduction matrix [a].

    f0 : float, optional (default is 1.0)
        Parameter that allows the dissipation term of the nonlinear 
        second-order dynamical system (dissipative Hamiltonian system) to be 
        controlled (damping that kills the transient response).

    dr : float, optional (default is 0.1)
        Sampling step of the continuous index parameter used in the 
        integration scheme.

    kde_bw_factor : float, optional (default is 1.0)
        Multiplier that modifies the computed KDE bandwidth (Silverman 
        rule-of-thumb).

    pot_method : int, optional (default is 2)
        Experimental.
        This is the most expensive part of the computation. 
        Methods 1-8 compute the same joint KDE using different algorithms.
        Method 2 is the most efficient.
        Method 9 computes a conditional (Nadaraya-Watson KDE) * marginal tanh 
        approximation. This is used when the distribution of one of the 
        variables is to be specified.
        Method 10 a computes conditional (Nadaraya-Watson KDE) * marginal KDE.

    Returns
    -------
    Z : ndarray of shape (nu, m)
        New reduced manifold sample matrix [Z].

    steps : list of t ndarrays of shape (nu, m)
        Ito steps for generated sample [Z].

    """
    nu, N = H.shape
    Y = np.random.randn(nu, N).dot(a)
    steps = []
    for j in range(0, t):
        Z, Y = _simulate_ito_step(Z, Y, H, basis, a, f0, dr, kde_bw_factor, 
                                  pot_method)
        # save ito steps
        steps.append(Z)
    return Z, steps

###############################################################################
def _simulate_ito_step(Z, Y, H, basis, a, f0, dr, kde_bw_factor, pot_method):
    """
    Evolve the ISDE for one step. Compute matrices [Z] and {Y] at end of step.
    
    Parameters
    ----------
    Z : ndarray of shape (nu, m)   
        Reduced random matrix [Z] evolved at start of current step.
    
    Y : ndarray of shape (nu, m)
        matrix [Y], evolved at start of current step.
    
    H : ndarray of shape (nu, n_samples)
        Typically, this is the normalized (PCA) data set. If the 
        non-normalized data set is used, this would be of shape 
        (n_features, n_samples).
    
    basis : ndarray of shape (n_samples, m)
        Reduced DMAPS basis.
    
    a : ndarray of shape (n_samples, m)
        Reduction matrix [a].
    
    f0 : float
        Parameter that allows the dissipation term of the nonlinear 
        second-order dynamical system (dissipative Hamiltonian system) to be 
        controlled (damping that kills the transient response).
    
    dr : float
        Sampling step of the continuous index parameter used in the 
        integration scheme.
    
    kde_bw_factor : float, optional (default is 1.0)
        Multiplier that modifies the computed KDE bandwidth (Silverman 
        rule-of-thumb).

    pot_method : int, optional (default is 2)
        Experimental.
        This is the most expensive part of the computation. 
        Methods 1-8 compute the same joint KDE using different algorithms.
        Method 2 is the most efficient.
        Method 9 computes a conditional (Nadaraya-Watson KDE) * marginal tanh 
        approximation. This is used when the distribution of one of the 
        variables is to be specified.
        Method 10 a computes conditional (Nadaraya-Watson KDE) * marginal KDE.
        
    Returns
    -------
    Znext : ndarray of shape (nu, m)
        Matrix [Z] evolved at end of current step.
    
    Ynext : ndarray of shape (nu, m)
        Matrix [Y] evolved at end of current step.
    
    """
    nu, N = H.shape
    b = f0*dr/4
    Weiner = dr**0.5 * np.random.randn(nu, N)
    dW = Weiner.dot(a)
    Zhalf = Z + (dr/2) * Y
    L = _get_L(H, np.dot(Zhalf, np.transpose(basis)), kde_bw_factor, 
               pot_method).dot(a)
    Ynext = (1-b)/(1+b) * Y + dr/(1+b) * L + np.sqrt(f0)/(1+b) * dW
    Znext = Zhalf + (dr/2) * Ynext    
    return Znext, Ynext

###############################################################################
def _sampling(Z0, H, basis, a, f0=1, dr=0.1, t='auto', num_samples=1, 
              parallel=False, n_jobs=-1, kde_bw_factor=1, pot_method=2, 
              verbose=True):
    """
    Calls the sampling function '_simulate_entire_ito' which evolves the ISDE 
    for 't' steps 'n' times. Obtain 'n' new samples at the end.
    If t is 'auto', compute required number of steps.
    
    Parameters
    ----------
    Z0 : ndarray of shape (nu, m)
        Reduced random matrix [Z] before evolution of ISDE.

    H : ndarray of shape (nu, n_samples)
        Typically, this is the normalized (PCA) data set. If the 
        non-normalized data set is used, this would be of shape 
        (n_features, n_samples).

    basis : ndarray of shape (n_samples, m)
        Reduced DMAPS basis.

    a : ndarray of shape (n_samples, m)
        Reduction matrix [a].

    f0 : float, optional (default is 1.0)
        Parameter that allows the dissipation term of the nonlinear 
        second-order dynamical system (dissipative Hamiltonian system) to be 
        controlled (damping that kills the transient response).

    dr : float, optional (default is 0.1)
        Sampling step of the continuous index parameter used in the 
        integration scheme.

    t : int/str, optional (default is 'auto')
        Number of steps that the Ito stochastic differential equation is 
        evolved for.
        If 'auto', number of steps is calculated internally.

    num_samples : int, optional (default is 1)
        Number of times that we sample the manifold. The actual number of 
        data points generated is equal to this 'n' times the original number 
        of points in the data set (n_samples).
    
    parallel : bool, optional (default is False)
        If True, run sampling in parallel.
    
    n_jobs : int, optional (default is -1)
        Number of jobs started by joblib.Parallel().
        Used if 'parallel' is True.
    
    kde_bw_factor : float, optional (default is 1.0)
        Multiplier that modifies the computed KDE bandwidth (Silverman 
        rule-of-thumb).
    
    pot_method : int, optional (default is 2)
        Experimental.
        This is the most expensive part of the computation. 
        Methods 1-8 compute the same joint KDE using different algorithms.
        Method 2 is the most efficient.
        Method 9 computes a conditional (Nadaraya-Watson KDE) * marginal tanh 
        approximation. This is used when the distribution of one of the 
        variables is to be specified.
        Method 10 a computes conditional (Nadaraya-Watson KDE) * marginal KDE.
    
    verbose : bool, optional (default is True)
        If True, print relevant information.
                
    Returns
    -------
    Zs : list of n ndarrays of shape (nu, m) each
         New reduced manifold samples matrix [Zs].
    
    Zs_steps : list n lists of t ndarrays of shape (nu, m)
        Ito steps for generated samples. FOR DEBUGGING.
    
    t : int
        Number of steps used in the Ito stochastic differential equation 
        evolution.
    
    """
    if verbose:
        print("\n\nPerforming Ito sampling.")
        print("------------------------")
        print(f"Projected data (Z) dimensions: {Z0.shape}")
    Zs, Zs_steps, t = _simulate_entire_ito(Z0, H, basis, a, f0, dr, t, 
                                           num_samples, parallel, n_jobs, 
                                           kde_bw_factor, pot_method, verbose)
    
    return Zs, Zs_steps, t

###############################################################################
def sampling(plom_dict):
    """
    PLoM wrapper for sampling function.

    Parameters
    ----------
    plom_dict : dictionary
        PLoM dictionary containing all elements computed by the PLoM framework.
        The relevant dictionary key gets updated by this function.

    Returns
    -------
    None.

    """
    projection_source = plom_dict['options']['projection_source']
    projection_target = plom_dict['options']['projection_target']
    
    if projection_source == "pca":
        X = plom_dict['pca']['training']
    elif projection_source == "scaling":
        X = plom_dict['scaling']['training']
    else:
        X = plom_dict['data']['training']
    
    if projection_target == "dmaps":
        basis = plom_dict['dmaps']['reduced_basis']
    elif projection_target == "pca":
        basis = plom_dict['pca']['training']
    
    f0            = plom_dict['input']['ito_f0']
    dr            = plom_dict['input']['ito_dr']
    t             = plom_dict['input']['ito_steps']
    num_samples   = plom_dict['input']['ito_num_samples']
    parallel      = plom_dict['options']['parallel']
    n_jobs        = plom_dict['options']['n_jobs']
    kde_bw_factor = plom_dict['options']['ito_kde_bw_factor']
    pot_method    = plom_dict['options']['ito_pot_method']
    verbose       = plom_dict['options']['verbose']
    Z             = plom_dict['ito']['Z0']
    a             = plom_dict['ito']['a']
    
    # X = np.copy(np.transpose(X))
    Zs, Zs_steps, t = _sampling(Z, X.T, basis, a, f0, dr, t, num_samples,
                                parallel, n_jobs, kde_bw_factor, pot_method, 
                                verbose)
    
    plom_dict['ito']['Zs']          = Zs
    plom_dict['ito']['Zs_steps']    = Zs_steps
    plom_dict['ito']['t']           = t

###############################################################################
def save_samples(plom_dict):
    
    samples_fname  = plom_dict['options']['samples_fname']
    job_desc       = plom_dict['job_desc']
    verbose        = plom_dict['options']['verbose']
    
    if verbose:
        print("\nSaving generated samples to file...")
    
    if samples_fname is None:
        samples_fname = (job_desc.replace(' ', '_') + '_samples_'
                        + time.strftime('%X').replace(':', '_') + '.txt')
        
    if samples_fname.endswith('.txt'):
        np.savetxt(samples_fname, plom_dict['data']['augmented'])
    elif samples_fname.endswith('.npy'):
        np.save(samples_fname, plom_dict['data']['augmented'])
    else:
        samples_fname = samples_fname + '.txt'
        np.savetxt(samples_fname, plom_dict['data']['augmented'])
    
    if verbose:
        print(f"Samples saved to {samples_fname}\n")
    
###############################################################################
def make_summary(plom_dict):
    """
    This function takes a populated PLoM dictionary and creates a summary of 
    the PLoM run.
    The summary is saved to the 'summary' key in the PLoM dictionary.

    Parameters
    ----------
    plom_dict : dict
        PLoM dictionary.

    Returns
    -------
    None.

    """
    job      = plom_dict['job_desc']
    inputs   = plom_dict['input']
    options  = plom_dict['options']
    data     = plom_dict['data']
    pca      = plom_dict['pca']
    dmaps    = plom_dict['dmaps']
    
    training_shape = data['training'].shape
    pca_shape      = pca['training'].shape
    sc_method      = options['scaling_method']
    
    summary = ["Job Summary\n-----------"]
    
    summary.append(f"Job: {job}\n")

    summary.append(f"Training data dimensions: {training_shape}\n")

    if options['scaling']:
        summary.append("Scaling")
        summary.append(f"Used '{sc_method}' method for scaling.\n")

    if options['pca']:
        summary.append("PCA")

        if options['pca_method']=='cum_energy':
            summary.append("Used Cumulative Energy Content criteria for PCA.")
        elif options['pca_method']=='eigv_cutoff':
            summary.append("Used specified cutoff value criteria for PCA.")
        elif options['pca_method']=='pca_dim':
            summary.append("Used specified PCA dimension.")
        summary.append(f"PCA features reduction: {training_shape[1]} -> " +
                       f"{pca_shape[1]}\n")

    if options['dmaps']:
        summary.append("DMAPS")
        summary.append(f"Input epsilon: {inputs['dmaps_epsilon']}")
        summary.append(f"Used epsilon: {dmaps['epsilon']:.2f}")
        summary.append("DMAPS eigenvalues: " +
                       f"{dmaps['eigenvalues'][1:dmaps['dimension']+1]}" + 
                       f" [{dmaps['eigenvalues'][dmaps['dimension']+1]:.4f}"+
                       " ...]")
        summary.append(f"Manifold dimension = {dmaps['dimension']}")
        summary.append(f"Used {dmaps['reduced_basis'].shape[1]} eigenvectors" +
                       " for projection.")
        summary.append("Projected data (Z) dimensions: " + 
                       f"{dmaps['training'].shape}\n")

    if data['augmented'] is not None:
        summary.append("Sampling")

        summary.append(f"Generated {inputs['ito_num_samples']} samples.")

        summary.append("Augmented data dimensions: " + 
                       f"{data['augmented'].shape}\n")
    
    plom_dict['summary'] = summary
    

###############################################################################
def save_summary(plom_dict, fname=None):
    if fname is None:
        fname = plom_dict['job_desc'] + "_plom_summary.txt"
    summary = '\n'.join(plom_dict['summary'])
    with open(fname, "w") as summary_file:
        summary_file.write(summary)
        
###############################################################################
def mse(X, Y, *, squared=True):
    """
    Mean squared error reconstruction loss.

    Parameters
    ----------
    X : ndarray of shape (n_samples,) or (n_samples, n_features)
        Ground truth (correct) target values.
    
    Y : array-like of shape (n_samples,) or (n_samples, n_features)
        Estimated target values.

    squared : bool, optional (default is True)
        If True, returns MSE value; if False, returns RMSE value.

    Returns
    -------
    error : float
        A non-negative floating point value (the best value is 0.0).

    """
    error = np.mean((X - Y) ** 2)
    return error if squared else np.sqrt(error)
    
###############################################################################
def _short_date():
    return datetime.now().replace(microsecond=0)

###############################################################################
def run(plom_dict):

## Start    
    start_time = datetime.now()
    job_desc       = plom_dict['job_desc']
    inputs         = plom_dict['input']
    options        = plom_dict['options']
    
    verbose        = options['verbose']
    scaling_opt    = options['scaling']
    pca_opt        = options['pca']
    dmaps_opt      = options['dmaps']
    projection_opt = options['projection']
    sampling_opt   = options['sampling']
    saving_opt     = options['save_samples']
    num_samples    = inputs['ito_num_samples']
    
    
    if verbose:
        print(f"\nPLoM run starting at {str(datetime.now()).split('.')[0]}")

## Scaling
    if scaling_opt:
        scale(plom_dict)

## PCA
    if pca_opt:
        pca(plom_dict)

## DMAPS
    if dmaps_opt:
        dmaps(plom_dict)

## Projection (Z)
    if projection_opt:
        sample_projection(plom_dict)

## Sampling
    if sampling_opt and num_samples != 0:
        sampling(plom_dict)

## Inverse Projection (Z)
    if projection_opt:
        inverse_sample_projection(plom_dict)

## Inverse PCA
    if pca_opt:
        inverse_pca(plom_dict)

## Inverse scaling
    if scaling_opt:
        inverse_scale(plom_dict)

## MSE
    rmse = mse(plom_dict['data']['training'], 
               plom_dict['data']['reconst_training'], 
               squared=False)
    plom_dict['data']['rmse'] = rmse
    if verbose:
        print(f'\nTraining data reconstruction RMSE = {rmse:.6E}')

## Summary
    make_summary(plom_dict)

## Saving samples
    if saving_opt:
        save_samples(plom_dict)
        save_summary(plom_dict)

## End
    end_time = datetime.now()
    if verbose:
        if plom_dict['data']['augmented'] is not None:
            print("\nAugmented data dimensions: ", 
                  f"{plom_dict['data']['augmented'].shape}")
        print(f"\n*** Total run time = {str(end_time-start_time)[:-3]} ***")
        print(f"\nPLoM run complete at {str(datetime.now()).split('.')[0]}")

###############################################################################
def run_dmaps(plom_dict):

## Start
    start_time = datetime.now()
    
    options        = plom_dict['options']
    
    verbose        = options['verbose']
    scaling_opt    = options['scaling']
    pca_opt        = options['pca']
    dmaps_opt      = options['dmaps']
    projection_opt = options['projection']


    if verbose:
        print("\nPLoM run (DMAPS ONLY) starting at ", 
              f"{str(datetime.now()).split('.')[0]}")

## Scaling
    if scaling_opt:
        scale(plom_dict)

## PCA
    if pca_opt:
        pca(plom_dict)

## DMAPS
    if dmaps_opt:
        dmaps(plom_dict)

## Projection (Z)
    if projection_opt:
        sample_projection(plom_dict)

## Inverse Projection (Z)
    if projection_opt:
        inverse_sample_projection(plom_dict)

## Inverse PCA
    if pca_opt:
        inverse_pca(plom_dict)

## Inverse scaling
    if scaling_opt:
        inverse_scale(plom_dict)

## MSE
    rmse = mse(plom_dict['data']['training'], 
               plom_dict['data']['reconst_training'], 
               squared=False)
    plom_dict['data']['rmse'] = rmse
    if verbose:
        print(f'\nTraining data reconstruction RMSE = {rmse:.6E}')

## Summary
    make_summary(plom_dict)

## End
    end_time = datetime.now()
    if verbose:
        print(f"\n*** Total run time = {str(end_time-start_time)[:-3]} ***")
        print("\nPLoM run (DMAPS ONLY) complete at ", 
              f"{str(datetime.now()).split('.')[0]}")

###############################################################################
def run_sampling(plom_dict):

## Start
    start_time = datetime.now()
    
    inputs         = plom_dict['input']
    options        = plom_dict['options']
    
    verbose        = options['verbose']
    scaling_opt    = options['scaling']
    pca_opt        = options['pca']
    projection_opt = options['projection']
    sampling_opt   = options['sampling']
    saving_opt     = options['save_samples']
    num_samples    = inputs['ito_num_samples']
    
    if verbose:
        print(f"\nPLoM run (SAMPLING ONLY) starting at \
{str(datetime.now()).split('.')[0]}")

## Check if DMAPS already run
    if plom_dict['ito']['Z0'] is None:
        raise Exception("Sampling aborted. DMAPS results not found. "+
                        "Run DMAPS before sampling.")

## Sampling
    if sampling_opt and num_samples != 0:
        sampling(plom_dict)

## Inverse Projection (Z)
    if projection_opt:
        inverse_sample_projection(plom_dict)

## Inverse PCA
    if pca_opt:
        inverse_pca(plom_dict)

## Inverse scaling
    if scaling_opt:
        inverse_scale(plom_dict)

## Summary
    make_summary(plom_dict)

## Saving samples
    if saving_opt:
        save_samples(plom_dict)
        save_summary(plom_dict)

## End
    end_time = datetime.now()
    if verbose:
        if plom_dict['data']['augmented'] is not None:
            print("\nAugmented data dimensions: ", 
                  f"{plom_dict['data']['augmented'].shape}")
        print(f"\n*** Total run time = {str(end_time-start_time)[:-3]} ***")
        print("\nPLoM run (SAMPLING ONLY) complete at ", 
              f"{str(datetime.now()).split('.')[0]}")

###############################################################################
####################                                       ####################
#################### Some tools to be used after PLoM runs ####################
####################                                       ####################
###############################################################################

###############################################################################
############################ Plotting functions ###############################
###############################################################################
def plot2D_reconstructed_training(plom_dict, i=0, j=1, size=9, pt_size=10, 
                                  color=['cmap','cmap']):
    training = plom_dict['data']['training'].T
    reconst_training = plom_dict['data']['reconst_training'].T
    [c1, c2] = color
    if c1 == 'cmap': c1 = range(training.shape[1])
    if c2 == 'cmap': c2 = range(training.shape[1])
    plt.figure(figsize=(size, size))
    t_plot = plt.scatter(training[i], training[j], s=pt_size, c=c1)
    t_r_plot = plt.scatter(reconst_training[i], reconst_training[j], 
                           s=pt_size, c=c2)
    plt.legend((t_plot, t_r_plot), ('Training', 'Reconstructed training'), 
               loc='best')
    plt.gca().set_aspect('equal')
    plt.title(f'Training vs reconstructed training, n={training.shape[1]}')
    plt.show()

###############################################################################
def plot2d_samples(plom_dict, i=0, j=1, size=9, pt_size=10):
    training = plom_dict['data']['training'].T
    samples = plom_dict['data']['augmented'].T
    N = training.shape[1]
    num_sample = plom_dict['input']['ito_num_samples']
    plt.figure(figsize=(size, size))
    plt.scatter(training[i], training[j], color='b', s=pt_size, 
                label='Training', marker="+")
    for k in range(num_sample):
        plt.scatter(samples[i, k*N:(k+1)*N], samples[j, k*N:(k+1)*N], 
                    color=np.random.rand(3), s=pt_size)
    plt.legend(loc='best')
    plt.gca().set_aspect('equal')
    plt.title('Training + New samples')
    plt.show()

###############################################################################
def plot3d_samples(plom_dict, i=0, j=1, size=9, pt_size=10):
    training = plom_dict['data']['training'].T
    samples = plom_dict['data']['augmented'].T
    
    fig = plt.figure(figsize=(size, size))
    ax = fig.add_subplot(111, projection='3d')
    ax.scatter(training[0], training[1], training[2], marker='o')
    ax.scatter(samples[0], samples[1], samples[2], marker='o')
    ax.set_xlabel('X-axis')
    ax.set_ylabel('Y-axis')
    ax.set_zlabel('Z-axis')
    plt.title('Training + New samples')
    plt.show()

###############################################################################
def plot_dmaps_eigenvalues(plom_dict, n=0, size=8, pt_size=10, save=False):
    evals = plom_dict['dmaps']['eigenvalues'][1:]
    m = plom_dict['dmaps']['dimension']
    if n == 0:
        n = max(min(2*m, evals.size), 10)
    elif n=='all':
        n = evals.size
    plt.figure(figsize=(size, size/2))
    plt.plot(range(m), evals[:m], c='r')
    plt.scatter(range(m), evals[:m], c='r', s=pt_size)
    plt.plot(range(m-1, n), evals[m-1:n], c='b', alpha=0.25)
    plt.scatter(range(m, n), evals[m:n], c='b', s=pt_size)
    plt.yscale("log")
    plt.title(f"DMAPS Eigenvalues (m={m})")
    if save:
        plt.savefig('DMAPS_eigenvalues.png')
    plt.show()

###############################################################################
def plot2D_dmaps_basis(plom_dict, vecs=[1,2], size=9, pt_size=10):
    evecs = plom_dict['dmaps']['basis'][:, vecs].T
    c = range(evecs.shape[1])
    plt.figure(figsize=(size, size))
    plt.scatter(evecs[0], evecs[1], s=pt_size, c=c)
    plt.title(f'DMAPS basi vectors {vecs[0]} (x) vs {vecs[1]} (y)')
    plt.show()

###############################################################################
def plot_pca_eigenvalues(plom_dict, log=True, save=False):
    evals = np.flip(plom_dict['pca']['eigvals'])
    evals = evals[evals > 1e-15]
    plt.figure(figsize=(12, 6))
    if log:
        plt.yscale('log')
        plt.ylim(evals.min()*0.9, evals.max()*1.1)
    plt.scatter(range(len(evals)), evals, s=7)
    plt.title("PCA Eigenvalues")
    plt.xticks(np.arange(0, len(evals), 5))
    plt.xlabel("Eigenvalue Index")
    plt.ylabel("Eigenvalue")
    plt.grid()
    if save:
        plt.savefig('PCA_eigenvalues.png')
    plt.show()

###############################################################################
########################## Loading and saving data  ###########################
###############################################################################
def load_dict(fname):
    file = open(fname, "rb")
    plom_dict = pickle.load(file)
    return plom_dict  

###############################################################################
def save_dict(plom_dict, fname=None):
    if fname is None:
        fname = plom_dict['job_desc'] + "_dict.plom"
    file = open(fname, "wb")
    pickle.dump(plom_dict, file)
    file.close()

###############################################################################
def save_epsvsm(plom_dict, fname=None):
    if fname is None:
        fname = plom_dict['job_desc'] + "_epsvsm.txt"
    eps = plom_dict['dmaps']['eps_vs_m']
    n = len(eps)
    with open(fname, "a") as eps_file:
        eps_file.write("\nEps         m\n-------------\n")
        for i in range(n):
            e = f"{eps[i][0]:.2f}"
            m = str(eps[i][1])
            s = e + (12-len(e))*" " + m + "\n"
            eps_file.write(s)
            
###############################################################################
def save_training(plom_dict, fname=None, fmt='txt'):
    """
    Save training data to txt or npy.

    Parameters
    ----------
    plom_dict : dict
        PLoM dictionary containing the training data.
    
    fname : str, optional (default is None)
        File name. If None, job description will be used instead.
    
    fmt : str, optional (default is 'txt')
        Format of saved file.
        If 'txt', save data to txt file.
        If 'npy', save data to npy file.

    Returns
    -------
    None.

    """
    if fname is None:
        fname = plom_dict['job_desc'] + "_training."
    if fmt == 'txt':
        np.savetxt(fname+fmt, plom_dict['data']['training'])
    elif fmt == 'npy':
        np.save(fname+fmt, plom_dict['data']['training'])
    else:
        raise Exception("'fmt' argument can be either 'txt' or 'npy'.")
    
###############################################################################
def _save_samples(plom_dict, fname=None, fmt='txt'):
    """
    Save generated samples to txt or npy.

    Parameters
    ----------
    plom_dict : dict
        PLoM dictionary containing the generated samples.
    
    fname : str, optional (default is None)
        File name. If None, job description will be used instead.
    
    fmt : str, optional (default is 'txt')
        Format of saved file.
        If 'txt', save data to txt file.
        If 'npy', save data to npy file.

    Returns
    -------
    None.

    """
    if fname is None:
        fname = plom_dict['job_desc'] + "_samples."
    if fmt == 'txt':
        np.savetxt(fname+fmt, plom_dict['data']['augmented'])
    elif fmt == 'npy':
        np.save(fname+fmt, plom_dict['data']['augmented'])
    else:
        raise Exception("'fmt' argument can be either 'txt' or 'npy'.")
    
###############################################################################
############################## Misc. functions  ###############################
###############################################################################
def print_summary(plom_dict):
    print(*plom_dict['summary'], sep='\n')
    
###############################################################################
def print_epsvsm(plom_dict):
    eps = plom_dict['dmaps']['eps_vs_m']
    n = len(eps)
    print("Eps         m\n-------------")
    for i in range(n):
        e = f"{eps[i][0]:.2f}"
        m = str(eps[i][1])
        s = e + (12-len(e))*" " + m
        print(s)
###############################################################################
def list_input_parameters(plom_dict=None):
    if plom_dict is None:
        input_params = list(initialize()['input'].keys())
    else:
        input_params = list(plom_dict['input'].keys())
    for _ in input_params:
        print(_)
###############################################################################
def list_options(plom_dict=None):
    if plom_dict is None:
        options = initialize()['options']
    else:
        options = list(plom_dict['options'].keys())
    for _ in options:
        print(_)

###############################################################################
def get_diffusion_distances(plom_dict, full_basis=False):
    if full_basis:
        data = plom_dict['dmaps']['basis'][:, 1:]
    else:
        data = plom_dict['dmaps']['reduced_basis']
    
    distances = distance_matrix(data, data)
    return distances

###############################################################################
def get_training(plom_dict):
    """
    Get training data from PLoM dictionary.

    Parameters
    ----------
    plom_dict : dict
        PLoM dictionary.

    Returns
    -------
    training : ndarray of shape (n_samples, n_features)
        Training data.

    """
    return plom_dict['data']['training']

###############################################################################
def get_reconst_training(plom_dict):
    """
    Get reconstructed training data from PLoM dictionary.

    Parameters
    ----------
    plom_dict : dict
        PLoM dictionary.

    Returns
    -------
    reconst_training : ndarray of shape (n_samples, n_features)
        Reconstructed training data.

    """
    return plom_dict['data']['reconst_training']

###############################################################################
def get_samples(plom_dict, k=0):
    """
    Get samples generated by PLoM.

    Parameters
    ----------
    plom_dict : dict
        PLoM dictionary.
        
    k : int, optional (default is 0)
        Number of samples requested where each sample is a dataset of size
        equal to the training dataset size.

    Returns
    -------
    samples : ndarray of shape (k*train_size, n_features)
        A matrix of generated samples. If k is 0, all samples are returned.
        If k is a positive integer, k samples are returned.

    """
    
    # check if 'k' is an int
    if not isinstance(k, int):
        raise TypeError("k (number of samples requested) must be an integer.")
    # check if 'k' is not negative
    if k < 0:
        raise ValueError("k (number of samples requested) must be 0 or ", 
                         "positive.")
    
    # k==0: all samples requested
    if k == 0:
        samples = plom_dict['data']['augmented']
        if samples is None:
            raise ValueError("Samples not found. Sampling not run?")
        if not isinstance(samples, np.ndarray):
            raise TypeError("'plom_dict['data']['augmented']' is not a 2D ", 
                            "Numpy array.")
    
    # k !=0: k samples requested
    else:
        try:
            train_size = plom_dict['data']['training'].shape[0]
        except:
            raise AttributeError("plom_dict['data']['training'] is not a 2D ", 
                                 "Numpy array. Unable to deduce training ", 
                                 "dataset size.")
        try:
            samples_size = plom_dict['data']['augmented'].shape[0]
        except:
            raise AttributeError("plom_dict['data']['augmented'] is not a 2D", 
                                 "Numpy array. Unable to deduce samples ", 
                                 "dataset size.")
        if k*train_size < samples_size:
            samples = plom_dict['data']['augmented'][:k*train_size]
        else:
            raise Exception("Too many samples requested (available samples = ",
                            f"{int(samples_size/train_size)}")

    return samples

###############################################################################
########################## Conditioning functions  ############################
###############################################################################

# def gaussian_kde(training, pt, kde_bw_factor=1, options=None):
#     N, n = training.shape
#     h = (4 / (N*(2+n))) ** (1/(n+4)) * kde_bw_factor
#     return h, (1/N * np.sum(np.exp((-1/2/h/h) * 
#                                    np.linalg.norm(training - pt, axis=1)**2)))

###############################################################################
# def plot_training_pdf(plom_dict, size=9, surface=True):
#     training  = plom_dict['training']
#     options   = plom_dict['options']
#     bw_factor = plom_dict['input']['kde_bw_factor']
    
#     xmin = 1.2 * min(training[:, 0])
#     xmax = 1.2 * max(training[:, 0])
#     ymin = 1.2 * min(training[:, 1])
#     ymax = 1.2 * max(training[:, 1])
#     xs, ys = np.meshgrid(np.linspace(xmin,xmax,100), 
#                           np.linspace(ymin,ymax,100))
#     xs_flat = xs.flatten()
#     ys_flat = ys.flatten()
#     grid = np.array((xs_flat, ys_flat)).T
    
#     pdf_flat = np.array([gaussian_kde(training, pt, bw_factor, options)[1] 
#                          for pt in grid])
#     pdf = pdf_flat.reshape(xs.shape)
#     h_used = gaussian_kde(training, [0,0], bw_factor, options)[0]
    
#     fig = plt.figure(figsize=(size, size))
#     ax = fig.add_subplot(111, projection='3d')
#     if surface:
#         ax.plot_surface(xs, ys, pdf, cmap=cm.coolwarm)
#     else:
#         ax.scatter(xs, ys, pdf)
#     ax.set_xlabel('X Label')
#     ax.set_ylabel('Y Label')
#     ax.set_zlabel('Z Label')
#     plt.title(f'Bandwidth used = {h_used}\n(Bandwidth factor = {bw_factor})')
#     plt.show()
    
###############################################################################
def _conditional_expectation(X, qoi_cols, cond_cols, cond_vals, sw=None,
                             verbose=True):
    """
    Get expectation of Q given W, E{Q | W=w0}.
    
    :arguments:
        X:         (np.ndarray) data matrix containing N>>1 samples
        cond_cols: (list) column indices of conditioning RVs
        cond_val:  (list) values of conditioning RVs
        qoi_cols:   (int) column index of RV for which expectation is computed
        
    :return:
        (float) conditional expectation of Q, E{Q | W=w0}
    """
    start = _short_date()
    if verbose:
        print('\n***********************************************************')
        print('Conditional expectation evaluation starting at', start)
    
    Nsim = X.shape[0]
    nw = np.atleast_1d(cond_cols).shape[0]
    nq = 1
    
    if verbose:
        print(f'\nEstimating the conditional expectation of <variable \
{qoi_cols}> conditioned on <variable{"" if nw==1 else "s"} {cond_cols}> = \
<{cond_vals}>.')
        print(f'Using N = {Nsim} samples.')
    
    ## Conditioning weights
    if sw is None:
        sw = (4 / (Nsim*(2+nw+nq))) ** (1/(4+nw+nq))
    if verbose:
        print("\nComputing conditioning weights.")
        print(f'Using bw = {sw:.6f} for conditioning weights.')
    weights = _get_conditional_weights(X[:, cond_cols], cond_vals, sw,
                                       verbose=verbose)
    
    ## Expectation evaluation
    if verbose:
        print("\nComputing expectation value.")
    q = X[:, qoi_cols]
    expn = np.atleast_1d(np.dot(weights, q))
    var = np.atleast_1d(np.dot(weights, q*q) - expn**2)
    if expn.shape[0] == 1:
        expn = expn[0]
        var = var[0]
    if verbose:
        print(f"\nConditional expected value of variable(s) {qoi_cols}: E = \
{expn}")
        print(f"\nConditional variance of variable(s) {qoi_cols}: Var = {var}")

    end = _short_date()
    if verbose:
        print('\nConditioning complete at', end)
        print('Time =', end-start)
    
    return expn, var

###############################################################################
def conditional_expectation(obj, qoi_cols, cond_cols, cond_vals, sw=None,
                             verbose=True):
    
    if isinstance(obj, dict):
        expectation, var = _conditional_expectation(obj['data']['augmented'], 
                                                    qoi_cols, cond_cols, 
                                                    cond_vals, sw, verbose)
    else:
        expectation, var = _conditional_expectation(obj, qoi_cols, cond_cols, 
                                                    cond_vals, sw, verbose)
    return expectation, var

###############################################################################
def _get_conditional_weights(W, w0, sw=None, nq=1, parallel=False, batches=2,
                              verbose=True):

    if W.ndim == 1:
        W = W[:, np.newaxis]
    Nsim, nw = W.shape
    w_std = np.std(W, axis=0)
    if sw is None:
        sw = (4 / (Nsim*(2+nw+nq))) ** (1/(4+nw+nq))
    
    if parallel:
        batch_size = int(Nsim / batches)
        r = Nsim % batch_size
        w_norms = Parallel(n_jobs=-1)(
            delayed(np.linalg.norm)(
                (W[i*batch_size: (i+1)*batch_size]-w0)/w_std, axis=1) 
            for i in range(batches))
        w_norms = (np.array(w_norms)).flatten()
        if r>1:
            w_norms = np.append(w_norms, 
                                np.linalg.norm((W[-r:]-w0)/w_std, axis=1))
        elif r==1:
            w_norms = np.append(w_norms, 
                                np.linalg.norm((W[-r:]-w0)/w_std, axis=0))
        w_norms = -1/(2*sw**2) * w_norms**2
    else:
        w_norms = -1/(2*sw**2) * np.linalg.norm((W-w0)/w_std, axis=1)**2

    w_dist = np.exp(w_norms - np.max(w_norms))
    w_dist_tot = np.sum(w_dist)
    return w_dist/w_dist_tot

###############################################################################
def _evaluate_kernels_sum(X, x, H, kernel_weights=None):
    X = np.asarray(X)
    x = np.asarray(x)
    H = np.asarray(H)
    
    if X.ndim == 1:
        X = X[:, np.newaxis]
    
    if H.ndim == 0: ## H is specified as a scalar, i.e. 1-D pdf
        H = np.atleast_2d(H**2)
    elif H.ndim == 1: ## H is specified as a list of n BWs, i.e. n-D pdf
        H = np.diag(H**2)
    
    N, n = X.shape
    
    if kernel_weights is None:
        kernel_weights = 1./N
    
    diff = X - x
    Hinv = np.linalg.inv(H)
    factor = 1/(2*np.pi)**(n/2)/np.sqrt(np.linalg.det(H)) 
    pdf = (factor * kernel_weights * 
           np.exp((-1/2) * np.sum(np.matmul(diff, Hinv) * diff, axis=1)))
    pdf = np.sum(pdf)
    return np.append(x, pdf)

###############################################################################
def _conditional_pdf(X, qoi_cols, cond_cols, cond_vals, grid=None, sw=None, 
                     sq=None, pdf_Npts=200, parallel=True, verbose=True):
    
    start = _short_date()
    if verbose:
        print('\n***********************************************************')
        print('Conditioning starting at', start)
    
    q = X[:, qoi_cols]
    Nsim = X.shape[0]
    nw = np.atleast_1d(cond_cols).shape[0]
    nq = np.atleast_1d(qoi_cols).shape[0]
    
    if verbose:
        print(f'\nEstimating the {"marginal" if nq==1 else "joint"} \
distribution of <variable{"" if nq==1 else "s"} {qoi_cols}> conditioned on \
<variable{"" if nw==1 else "s"} {cond_cols}> = <{cond_vals}>.')
        print(f'Using N = {Nsim} samples.')
    
    ## Conditioning weights
    if sw is None:
        sw = (4 / (Nsim*(2+nw+nq))) ** (1/(4+nw+nq))
    if verbose:
        print("\nComputing conditioning weights.")
        print(f'Using bw = {sw:.6f} for conditioning weights.')
    weights = _get_conditional_weights(X[:, cond_cols], cond_vals, sw,
                                       verbose=verbose)
    
    ## PDF evaluation grid
    if grid is None:
        if nq == 1:
            grid = np.linspace(min(q), max(q), pdf_Npts)
        else:
            axes_pts = np.linspace(np.min(q, axis=0), np.max(q, axis=0), 
                                   pdf_Npts, axis=0)
            grid = np.asarray(np.meshgrid(*axes_pts.T))
            grid = grid.reshape(nq, -1).T
        if verbose:
            print(f'\nGenerating PDF evaluation grid from data ({pdf_Npts} \
pts per dimension, {grid.shape[0]} points in total).')
    else:            
        grid = np.asarray(grid)
        if verbose:
            print(f'\nUsing specified grid for PDF evaluation \
({grid.shape[0]} points).')

    ## KDE bandwidth
    if sq is None:
        q_std = np.std(q, axis=0)
        sq = np.asarray((4 / (Nsim*(2+nw+nq))) ** (1/(4+nw+nq)) * q_std)
        if sq.ndim == 0:
            H = np.atleast_2d(sq**2)
        else:
            H = np.diag(sq**2)
        if verbose:
            print(f'\nComputing kernel bandwidth{"" if nq==1 else "s"} using \
Silverman\'s rule of thumb.')
            with np.printoptions(precision=6):
                print(f'Bandwidth used = {np.diag(np.sqrt(H))}')
    else:
        sq = np.asarray(sq)
        ## if H is specified as a scalar, i.e. 1-D pdf or isotropic n-D pdf
        if sq.ndim == 0:
            H = np.eye(nq)*(sq**2)
        ## if H is specified as a list of n BWs, i.e. non-isotropic n-D pdf
        elif sq.ndim == 1:
            if sq.shape[0] == 1: ## assume same bw for all variables
                H = np.eye(nq)*(sq**2)
            else:
                if sq.shape[0] != nq:
                    raise ValueError("Number of specified anisotropic \
bandwidths must be equal to the number of conditioned variables (QoIs).")
                H = np.diag(sq**2)
        if verbose:
            print(f'\nUsing specified kernel bandwidth{"s" if nq==1 else ""}.')
            print(f'Bandwidth used = {np.diag(np.sqrt(H))}')
    
    ## KDE evaluation
    if parallel:
        if verbose:
            print(f'\nEvaluating KDE on {grid.shape[0]} points in parallel.')
        result = Parallel(n_jobs=-1)(
            delayed(_evaluate_kernels_sum)(q, grid[i], H, weights) 
            for i in range(len(grid)))
    else:
        if verbose:
            print(f'\nEvaluating KDE on {grid.shape[0]} points.')
        result = []
        for x in grid:
            result.append(_evaluate_kernels_sum(q, x, H, weights))
    
    end = _short_date()
    if verbose:
        print('\nConditioning complete at', end)
        print('Time =', end-start)
    
    return np.array(result)

###############################################################################
def conditional_pdf(obj, qoi_cols, cond_cols, cond_vals, grid=None, sw=None, 
                    sq=None, pdf_Npts=200, parallel=True, verbose=True): 
    if isinstance(obj, dict):
        pdf = _conditional_pdf(obj['data']['augmented'], qoi_cols, cond_cols, 
                               cond_vals, grid, sw, sq, pdf_Npts, parallel, 
                               verbose)
    else:
        pdf = _conditional_pdf(obj, qoi_cols, cond_cols, cond_vals, grid, sw, 
                               sq, pdf_Npts, parallel, verbose)
    return pdf

###############################################################################
