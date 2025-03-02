# Copyright (c) 2016 by Mike Jarvis and the other collaborators on GitHub at
# https://github.com/rmjarvis/Piff  All rights reserved.
#
# Piff is free software: Redistribution and use in source and binary forms
# with or without modification, are permitted provided that the following
# conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice, this
#    list of conditions and the disclaimer given in the accompanying LICENSE
#    file.
# 2. Redistributions in binary form must reproduce the above copyright notice,
#    this list of conditions and the disclaimer given in the documentation
#    and/or other materials provided with the distribution.

from __future__ import print_function
import numpy as np
import piff
import os
import galsim
import fitsio
import yaml
import subprocess

from piff_test_helper import get_script_name, timer, CaptureLog


@timer
def test_twodstats():
    """Make sure we can execute and print a readout of the plot
    """
    if __name__ == '__main__':
        logger = piff.config.setup_logger(2)
    else:
        logger = None

    model = piff.Gaussian(fastfit=True)
    interp = piff.Polynomial(order=1)  # should find that order=1 is better
    # create background model
    stars, true_model = generate_starlist(100)
    psf = piff.SimplePSF(model, interp)
    psf.fit(stars, None, None)
    stars = psf.stars  # These have the right fit parameters

    # check the coeffs of sigma and g2, which are actually linear fits
    # skip g1 since it is actually a 2d parabola
    # factor of 0.263 is to account for going from pixel xy to wcs uv
    np.testing.assert_almost_equal(psf.interp.coeffs[0].flatten(),
                                   np.array([0.4, 0, 1. / (0.263 * 2048), 0]), decimal=4)
    np.testing.assert_almost_equal(psf.interp.coeffs[2].flatten(),
                                   np.array([-0.1 * 1000 / 2048, 0, 0.1 / (0.263 * 2048), 0]),
                                   decimal=4)

    stats = piff.TwoDHistStats(nbins_u=5, nbins_v=5)  # implicitly np.median
    stats.compute(psf, stars, logger=logger)
    # check the twodhists
    # get the average value in the bin
    u_i = 3
    v_i = 3
    icen = stats.twodhists['u'][v_i, u_i] / 0.263
    jcen = stats.twodhists['v'][v_i, u_i] / 0.263
    print('icen = ',icen)
    print('jcen = ',jcen)
    icenter = 1000
    jcenter = 2000
    # the average value in the bin should match up with the model for the average coordinates
    sigma, g1, g2 = psf_model(icen, jcen, icenter, jcenter)
    gsq = g1**2 + g2**2
    T = 2*sigma**2 * (1+gsq)/(1-gsq)
    T_average = stats.twodhists['T'][v_i, u_i]
    g1_average = stats.twodhists['g1'][v_i, u_i]
    g2_average = stats.twodhists['g2'][v_i, u_i]
    # assert equal to 4th decimal
    print('T, g1, g2 = ',[T,g1,g2])
    print('av T, g1, g2 = ',[T_average,g1_average,g2_average])
    np.testing.assert_almost_equal([T, g1, g2], [T_average, g1_average, g2_average],
                                   decimal=2)

    # Test the plotting and writing
    twodstats_file = os.path.join('output','twodstats.pdf')
    stats.write(twodstats_file)

    with np.testing.assert_raises(ValueError):
        stats.write()  # If not given in constructor, must give file name here.

    # repeat for whisker
    stats = piff.WhiskerStats(nbins_u=21, nbins_v=21, reducing_function='np.mean')
    stats.compute(psf, stars)
    # Test the plotting and writing
    whisker_file = os.path.join('output','whiskerstats.pdf')
    stats.write(whisker_file)
    with np.testing.assert_raises(ValueError):
        stats.write()

    # With large number of bins, many will have no objects.  This is ok.
    # Also, can use other np functions like max, std, instead to get different stats
    # Not sure when these would be useful, but they are allowed.
    # And, check usage where file_name is given in init.
    twodstats_file2 = os.path.join('output','twodstats.pdf')
    stats2 = piff.TwoDHistStats(nbins_u=50, nbins_v=50, reducing_function='np.std',
                                file_name=twodstats_file2)
    with np.testing.assert_raises(RuntimeError):
        stats2.write()  # Cannot write before compute
    stats2.compute(psf, stars, logger=logger)
    stats2.write()

    whisker_file2 = os.path.join('output','whiskerstats.pdf')
    stats2 = piff.WhiskerStats(nbins_u=100, nbins_v=100, reducing_function='np.max',
                               file_name=whisker_file2)
    with np.testing.assert_raises(RuntimeError):
        stats2.write()  # Cannot write before compute
    stats2.compute(psf, stars)
    stats2.write()

@timer
def test_shift_cmap():
    from matplotlib import cm

    # test vmax and vmin center issues
    vmin = -1
    vmax = 8
    center = 2

    # color map vmin > center
    cmap = piff.TwoDHistStats._shift_cmap(vmin, vmax, vmin - 1)
    assert cmap == cm.Reds

    # color map vmax < center
    cmap = piff.TwoDHistStats._shift_cmap(vmin, vmax, vmax + 1)
    assert cmap == cm.Blues_r

    # test without center
    cmap = piff.TwoDHistStats._shift_cmap(vmin, vmax)
    midpoint = (0 - vmin) * 1. / (vmax - vmin)
    unshifted_cmap = cm.RdBu_r
    # check segment data
    # NOTE: that because of interpolation cmap(midpont) does not have to equal
    # unshifted_cmap(0.5)
    for val, color in zip(unshifted_cmap(0.5), ['red', 'green', 'blue', 'alpha']):
        assert midpoint == cmap._segmentdata[color][128][0]
        assert val == cmap._segmentdata[color][128][1]
        assert val == cmap._segmentdata[color][128][2]
    # but edge values are the same
    assert cmap(0.) == unshifted_cmap(0.)
    assert cmap(1.) == unshifted_cmap(1.)

    # test with center
    cmap = piff.TwoDHistStats._shift_cmap(vmin, vmax, center)
    midpoint = (center - vmin) * 1. / (vmax - vmin)
    unshifted_cmap = cm.RdBu_r
    for val, color in zip(unshifted_cmap(0.5), ['red', 'green', 'blue', 'alpha']):
        assert midpoint == cmap._segmentdata[color][128][0]
        assert val == cmap._segmentdata[color][128][1]
        assert val == cmap._segmentdata[color][128][2]
    assert cmap(0.) == unshifted_cmap(0.)
    assert cmap(1.) == unshifted_cmap(1.)

    # what if vmax < vmin?
    cmap = piff.TwoDHistStats._shift_cmap(vmax, vmin, center)
    midpoint = 1. - (center - vmax) * 1. / (vmin - vmax)
    unshifted_cmap = cm.RdBu_r
    for val, color in zip(unshifted_cmap(0.5), ['red', 'green', 'blue', 'alpha']):
        assert midpoint == cmap._segmentdata[color][128][0]
        assert val == cmap._segmentdata[color][128][1]
        assert val == cmap._segmentdata[color][128][2]
    assert cmap(0.) == unshifted_cmap(1.)
    assert cmap(1.) == unshifted_cmap(0.)

def make_star(icen=500, jcen=700, ccdnum=28,
              sigma=1, g1=0, g2=0,
              pixel_to_focal=False,
              properties={},
              fit_kwargs={}):

    properties['ccdnum'] = ccdnum
    # setting scale is crucial
    stardata = piff.Star.makeTarget(x=icen, y=jcen, properties=properties,
                                    scale=0.263)
    # apply Gaussian sigma, g1, g2
    params = np.array([sigma, g1, g2])

    starfit = piff.StarFit(params, **fit_kwargs)

    star = piff.Star(stardata.data, starfit)

    return star

def psf_model(icens, jcens, icenter, jcenter):
    sigmas = icens * (2. - 1.) / 2048. + 0.4
    g1s = ((jcens - jcenter) / 4096.) ** 2 * -0.2
    g2s = (icens - icenter) * 0.1 / 2048.
    return sigmas, g1s, g2s

def generate_starlist(n_samples=500):
    # create n_samples images from the 63 ccds and pixel coordinates
    np_rng = np.random.RandomState(1234)
    icens = np_rng.randint(100, 2048, n_samples)
    jcens = np_rng.randint(100, 4096, n_samples)
    ccdnums = np_rng.randint(1, 63, n_samples)
    icenter = 1000
    jcenter = 2000

    # throw out any icens and jcens that are within 400 pixels of the center
    conds = (np.abs(icens - icenter) > 400) | (np.abs(jcens - jcenter) > 400)
    icens = icens[conds]
    jcens = jcens[conds]
    ccdnums = ccdnums[conds]

    sigmas, g1s, g2s = psf_model(icens, jcens, icenter, jcenter)

    # throw in a 2d polynomial function for sigma g1 and g2
    # all sigma > 0, all g1 < 0, and g2 straddles.

    star_list = [make_star(icen, jcen, ccdnum, sigma, g1, g2)
                 for icen, jcen, ccdnum, sigma, g1, g2
                 in zip(icens, jcens, ccdnums, sigmas, g1s, g2s)]

    # load up model and draw the stars
    model = piff.Gaussian(fastfit=True)
    star_list = [model.draw(star) for star in star_list]
    star_list = [model.initialize(star) for star in star_list]
    star_list = [model.fit(star) for star in star_list]

    return star_list, model

@timer
def setup():
    """Build an input image and catalog used by a few tests below.
    """
    wcs = galsim.TanWCS(
            galsim.AffineTransform(0.26, 0.05, -0.08, -0.24, galsim.PositionD(1024,1024)),
            #galsim.AffineTransform(0.26, 0., 0., 0.26, galsim.PositionD(1024,1024)),
            galsim.CelestialCoord(5 * galsim.arcmin, -25 * galsim.degrees)
            )

    # Make the image (copied from test_single_image in test_simple.py)
    image = galsim.Image(2048, 2048, wcs=wcs)

    # Where to put the stars.
    x_list = [ 123.12, 345.98, 567.25, 1094.94, 924.15, 1532.74, 1743.11, 888.39, 1033.29, 1409.31 ]
    y_list = [ 345.43, 567.45, 1094.32, 924.29, 1532.92, 1743.83, 888.83, 1033.19, 1409.20, 123.11 ]

    # Draw a Gaussian PSF at each location on the image.
    sigma = 1.3
    g1 = 0.23
    g2 = -0.17
    du = 0.09  # in arcsec
    dv = -0.07
    flux = 123.45
    psf = galsim.Gaussian(sigma=sigma).shear(g1=g1, g2=g2).shift(du,dv) * flux
    for x, y in zip(x_list, y_list):
        bounds = galsim.BoundsI(int(x-31), int(x+32), int(y-31), int(y+32))
        offset = galsim.PositionD(x-int(x)-0.5, y-int(y)-0.5)
        psf.drawImage(image=image[bounds], method='no_pixel', offset=offset)
    image.addNoise(galsim.GaussianNoise(rng=galsim.BaseDeviate(1234), sigma=1e-6))

    # Write out the image to a file
    image_file = os.path.join('output','test_stats_image.fits')
    image.write(image_file)

    # Write out the catalog to a file
    dtype = [ ('x','f8'), ('y','f8') ]
    data = np.empty(len(x_list), dtype=dtype)
    data['x'] = x_list
    data['y'] = y_list
    cat_file = os.path.join('output','test_stats_cat.fits')
    fitsio.write(cat_file, data, clobber=True)

@timer
def test_twodstats_config():
    """Test running stats through a config file.
    """
    if __name__ == '__main__':
        logger = piff.config.setup_logger(verbose=2)
    else:
        logger = piff.config.setup_logger(log_file='output/test_twodstats_config.log')

    image_file = os.path.join('output','test_stats_image.fits')
    cat_file = os.path.join('output','test_stats_cat.fits')
    psf_file = os.path.join('output','test_twodstats.fits')
    twodhist_file = os.path.join('output','test_twodhiststats.pdf')
    twodhist_std_file = os.path.join('output','test_twodhiststats_std.pdf')
    config = {
        'input' : {
            'image_file_name' : image_file,
            'cat_file_name' : cat_file,
            'stamp_size' : 48
        },
        'psf' : {
            'model' : { 'type' : 'Gaussian',
                        'fastfit': True,
                        'include_pixel': False },
            'interp' : { 'type' : 'Mean' },
        },
        'output' : {
            'file_name' : psf_file,
            'stats' : [
                {
                    'type': 'TwoDHist',
                    'file_name': twodhist_file,
                    'nbins_u': 3,
                    'nbins_v': 3,
                },
                {
                    'type': 'TwoDHist',
                    'file_name': twodhist_std_file,
                    'reducing_function': 'np.std',
                    'nbins_u': 3,
                    'nbins_v': 3,
                },
            ]
        }
    }
    piff.piffify(config, logger)
    assert os.path.isfile(twodhist_file)
    assert os.path.isfile(twodhist_std_file)

    # repeat with plotify function
    os.remove(twodhist_file)
    os.remove(twodhist_std_file)
    piff.plotify(config, logger)
    assert os.path.isfile(twodhist_file)
    assert os.path.isfile(twodhist_std_file)



@timer
def test_rhostats_config():
    """Test running stats through a config file.
    """
    if __name__ == '__main__':
        logger = piff.config.setup_logger(verbose=2)
    else:
        logger = piff.config.setup_logger(log_file='output/test_rhostats_config.log')

    image_file = os.path.join('output','test_stats_image.fits')
    cat_file = os.path.join('output','test_stats_cat.fits')
    psf_file = os.path.join('output','test_rhostats.fits')
    rho_file = os.path.join('output','test_rhostats.pdf')
    config = {
        'input' : {
            'image_file_name' : image_file,
            'cat_file_name' : cat_file,
            'stamp_size' : 48
        },
        'psf' : {
            'model' : { 'type' : 'Gaussian',
                        'fastfit': True,
                        'include_pixel': False },
            'interp' : { 'type' : 'Mean' },
        },
        'output' : {
            'file_name' : psf_file,
            'stats' : {  # Note: stats doesn't have to be a list.
                'type': 'Rho',
                'file_name': rho_file,
                'min_sep': 30,
                'max_sep': 600,
                'sep_units': 'arcsec',
                'bin_type': 'Linear',
                'bin_size': 30,
            }
        },
    }
    piff.piffify(config, logger)
    assert os.path.isfile(rho_file)

    # repeat with plotify function
    os.remove(rho_file)
    piff.plotify(config, logger)
    assert os.path.isfile(rho_file)

    # Test rho statistics directly.
    min_sep = 1
    max_sep = 100
    bin_size = 0.1
    psf = piff.read(psf_file)
    orig_stars, wcs, pointing = piff.Input.process(config['input'], logger)
    stats = piff.RhoStats(min_sep=min_sep, max_sep=max_sep, bin_size=bin_size)
    with np.testing.assert_raises(RuntimeError):
        stats.write('dummy')  # Cannot write before compute
    stats.compute(psf, orig_stars)

    rhos = [stats.rho1, stats.rho2, stats.rho3, stats.rho4, stats.rho5]
    for rho in rhos:
        # Test the range of separations
        radius = np.exp(rho.logr)
        np.testing.assert_array_less(radius, max_sep)
        np.testing.assert_array_less(min_sep, radius)
        # bin_size is reduced slightly to get integer number of bins
        assert rho.bin_size < bin_size
        assert np.isclose(rho.bin_size, bin_size, rtol=0.1)
        np.testing.assert_array_almost_equal(np.diff(rho.logr), rho.bin_size, decimal=5)

        # Test that the max absolute value of each rho isn't crazy
        np.testing.assert_array_less(np.abs(rho.xip), 1)

        # # Check that each rho isn't precisely zero. This means the sum of abs > 0
        np.testing.assert_array_less(0, np.sum(np.abs(rho.xip)))

    # Test using the piffify executable
    os.remove(rho_file)
    config['verbose'] = 0
    with open('rho.yaml','w') as f:
        f.write(yaml.dump(config, default_flow_style=False))
    piffify_exe = get_script_name('piffify')
    p = subprocess.Popen( [piffify_exe, 'rho.yaml'] )
    p.communicate()
    assert os.path.isfile(rho_file)

    # Test using the plotify executable
    os.remove(rho_file)
    plotify_exe = get_script_name('plotify')
    p = subprocess.Popen( [plotify_exe, 'rho.yaml'] )
    p.communicate()
    assert os.path.isfile(rho_file)

    # test running plotify with dir in config, with no logger, and with a modules specification.
    # (all to improve test coverage)
    config['output']['dir'] = '.'
    config['modules'] = [ 'custom_wcs' ]
    os.remove(rho_file)
    piff.plotify(config)
    assert os.path.isfile(rho_file)


@timer
def test_shapestats_config():
    """Test running stats through a config file.
    """
    if __name__ == '__main__':
        logger = piff.config.setup_logger(verbose=2)
    else:
        logger = piff.config.setup_logger(log_file='output/test_shapestats_config.log')

    image_file = os.path.join('output','test_stats_image.fits')
    cat_file = os.path.join('output','test_stats_cat.fits')
    psf_file = os.path.join('output','test_shapestats.fits')
    shape_file = os.path.join('output','test_shapestats.pdf')
    config = {
        'input' : {
            'image_file_name' : image_file,
            'cat_file_name' : cat_file,
            'stamp_size' : 48
        },
        'psf' : {
            'model' : { 'type' : 'Gaussian',
                        'fastfit': True,
                        'include_pixel': False },
            'interp' : { 'type' : 'Mean' },
        },
        'output' : {
            'file_name' : psf_file,
            'stats' : [
                {
                    'type': 'ShapeHist',
                    'file_name': shape_file
                },
            ]
        },
    }
    piff.piffify(config, logger)
    assert os.path.isfile(shape_file)

    # repeat with plotify function
    os.remove(shape_file)
    piff.plotify(config, logger)
    assert os.path.isfile(shape_file)

    # Test ShapeHistStats directly
    psf = piff.read(psf_file)
    shapeStats = piff.ShapeHistStats(nbins=5)  # default is sqrt(nstars)
    orig_stars, wcs, pointing = piff.Input.process(config['input'], logger)
    with np.testing.assert_raises(RuntimeError):
        shapeStats.write()  # Cannot write before compute
    shapeStats.compute(psf, orig_stars)
    shapeStats.plot(histtype='bar', log=True)  # can supply additional args for matplotlib

    # test their characteristics
    sigma = 1.3  # (copied from setup())
    g1 = 0.23
    g2 = -0.17
    gsq = g1**2 + g2**2
    T = 2*sigma**2 * (1+gsq)/(1-gsq)
    np.testing.assert_array_almost_equal(T, shapeStats.T, decimal=4)
    np.testing.assert_array_almost_equal(T, shapeStats.T_model, decimal=3)
    np.testing.assert_array_almost_equal(g1, shapeStats.g1, decimal=4)
    np.testing.assert_array_almost_equal(g1, shapeStats.g1_model, decimal=3)
    np.testing.assert_array_almost_equal(g2, shapeStats.g2, decimal=4)
    np.testing.assert_array_almost_equal(g2, shapeStats.g2_model, decimal=3)


@timer
def test_starstats_config():
    """Test running stats through a config file.
    """
    if __name__ == '__main__':
        logger = piff.config.setup_logger(verbose=2)
    else:
        logger = piff.config.setup_logger(log_file='output/test_starstats_config.log')

    image_file = os.path.join('output','test_stats_image.fits')
    cat_file = os.path.join('output','test_stats_cat.fits')
    psf_file = os.path.join('output','test_starstats.fits')
    star_file = os.path.join('output', 'test_starstats.pdf')
    star_noadjust_file = os.path.join('output', 'test_starstats_noadjust.pdf')
    config = {
        'input' : {
            'image_file_name' : image_file,
            'cat_file_name' : cat_file,
            'stamp_size' : 48
        },
        'select' : {
            'reserve_frac': 0.2,
            'seed': 12345,
        },
        'psf' : {
            'model' : { 'type' : 'Gaussian',
                        'fastfit': True,
                        'include_pixel': False },
            'interp' : { 'type' : 'Mean' },
        },
        'output' : {
            'file_name' : psf_file,
            'stats' : [
                {
                    'type': 'StarImages',
                    'file_name': star_file,
                    'nplot': 5,
                    'adjust_stars': True,
                }
            ]
        }
    }
    piff.piffify(config, logger)
    assert os.path.isfile(star_file)

    # repeat with plotify function
    os.remove(star_file)
    piff.plotify(config, logger)
    assert os.path.isfile(star_file)

    # repeat with deprecated name
    os.remove(star_file)
    config['output']['stats'][0]['type'] = 'Star'
    with CaptureLog() as cl:
        piff.plotify(config, cl.logger)
    assert os.path.isfile(star_file)
    assert 'Star is deprecated' in cl.output
    config['output']['stats'][0]['type'] = 'StarImages'

    # check default nplot
    psf = piff.read(psf_file)
    starStats = piff.StarStats()
    orig_stars, wcs, pointing = piff.Input.process(config['input'], logger=logger)
    orig_stars = piff.Select.process(config['select'], orig_stars, logger=logger)
    with np.testing.assert_raises(RuntimeError):
        starStats.write()  # Cannot write before compute
    starStats.compute(psf, orig_stars)
    assert starStats.nplot == len(starStats.stars)
    assert starStats.nplot == len(starStats.models)
    assert starStats.nplot == len(starStats.indices)
    np.testing.assert_array_equal(starStats.stars[2].image.array,
                                  orig_stars[starStats.indices[2]].image.array)

    # check nplot = 6
    starStats = piff.StarStats(nplot=6)
    starStats.compute(psf, orig_stars)
    assert len(starStats.stars) == 6

    # check nplot >> len(stars)
    starStats = piff.StarStats(nplot=1000000)
    starStats.compute(psf, orig_stars)
    assert len(starStats.stars) == len(orig_stars)
    # if use all stars, no randomness
    np.testing.assert_array_equal(starStats.stars[3].image.array, orig_stars[3].image.array)
    np.testing.assert_array_equal(starStats.indices, np.arange(len(orig_stars)))
    starStats.plot()  # Make sure this runs without error and in finite time.

    # check nplot = 0
    starStats = piff.StarStats(nplot=0)
    starStats.compute(psf, orig_stars)
    assert len(starStats.stars) == len(orig_stars)
    # if use all stars, no randomness
    np.testing.assert_array_equal(starStats.stars[3].image.array, orig_stars[3].image.array)
    np.testing.assert_array_equal(starStats.indices, np.arange(len(orig_stars)))
    starStats.plot()  # Make sure this runs without error.

    # With include_reserve=False, only 8 stars
    print('All stars: n=',len(starStats.stars))  # 10 stars total
    assert len(starStats.stars) == 10
    starStats = piff.StarStats(nplot=0, include_reserve=False)
    starStats.compute(psf, orig_stars)
    assert len(starStats.stars) == 8
    starStats.plot()  # Make sure this runs without error.

    # With only_reserve=True, only 2 stars
    starStats = piff.StarStats(nplot=0, only_reserve=True)
    starStats.compute(psf, orig_stars)
    assert len(starStats.stars) == 2
    starStats.plot()  # Make sure this runs without error.

    # rerun with adjust stars and see if it did the right thing
    # first with adjust_stars == False
    starStats = piff.StarStats(nplot=0, adjust_stars=False)
    starStats.compute(psf, orig_stars, logger=logger)
    fluxs_noadjust = np.array([s.fit.flux for s in starStats.stars])
    ds_noadjust = np.array([s.fit.center for s in starStats.stars])
    # check that fluxes 1
    np.testing.assert_array_equal(fluxs_noadjust, 1)
    # check that ds are 0
    np.testing.assert_array_equal(ds_noadjust, 0)

    # now with adjust_stars == True
    starStats = piff.StarStats(nplot=0, adjust_stars=True)
    starStats.compute(psf, orig_stars, logger=logger)
    fluxs_adjust = np.array([s.fit.flux for s in starStats.stars])
    ds_adjust = np.array([s.fit.center for s in starStats.stars])
    # copy the right values from setup()
    du = 0.09
    dv = -0.07
    flux = 123.45
    # compare fluxes
    np.testing.assert_allclose(fluxs_adjust, flux, rtol=1e-4)
    np.testing.assert_allclose(ds_adjust[:,0], du, rtol=1e-4)
    np.testing.assert_allclose(ds_adjust[:,1], dv, rtol=1e-4)

    # do once with adjust_stars = False to graphically demonstrate
    config['output']['stats'][0]['file_name'] = star_noadjust_file
    config['output']['stats'][0]['adjust_stars'] = False
    piff.plotify(config, logger)
    assert os.path.isfile(star_noadjust_file)

@timer
def test_hsmcatalog():
    """Test HSMCatalog stats type.
    """
    if __name__ == '__main__':
        logger = piff.config.setup_logger(verbose=2)
    else:
        logger = piff.config.setup_logger(log_file='output/test_hsmcatalog.log')

    image_file = os.path.join('output','test_stats_image.fits')
    cat_file = os.path.join('output','test_stats_cat.fits')
    psf_file = os.path.join('output','test_starstats.fits')
    hsm_file = os.path.join('output', 'test_hsmcatalog.fits')
    config = {
        'input' : {
            'image_file_name' : image_file,
            'cat_file_name' : cat_file,
            'stamp_size' : 48,
        },
        'select' : {
            'reserve_frac' : 0.2,
            'seed' : 123
        },
        'psf' : {
            'model' : { 'type' : 'Gaussian',
                        'fastfit': True,
                        'include_pixel': False },
            'interp' : { 'type' : 'Mean' },
        },
        'output' : {
            'file_name' : psf_file,
            'stats' : [
                {
                    'type': 'HSMCatalog',
                    'file_name': hsm_file,
                }
            ]
        }
    }
    piff.piffify(config, logger)
    assert os.path.isfile(hsm_file)

    data, header = fitsio.read(hsm_file, header=True)
    for col in ['ra', 'dec', 'x', 'y', 'u', 'v',
                'T_data', 'g1_data', 'g2_data',
                'T_model', 'g1_model', 'g2_model',
                'flux', 'reserve', 'flag_data', 'flag_model']:
        assert len(data[col]) == 10
    true_data = fitsio.read(cat_file)

    assert header['PIFF_VERSION'] == piff.__version__

    np.testing.assert_allclose(data['x'], true_data['x'])
    np.testing.assert_allclose(data['y'], true_data['y'])
    np.testing.assert_allclose(data['flux'], 123.45, atol=0.001)
    print('reserve = ',data['reserve'])
    print('nreserve = ',np.sum(data['reserve']))
    print('ntot = ',len(data['reserve']))
    assert np.sum(data['reserve']) == int(0.2 * len(data['reserve']))
    np.testing.assert_allclose(data['T_model'], data['T_data'], rtol=1.e-4)
    np.testing.assert_allclose(data['g1_model'], data['g1_data'], rtol=1.e-4)
    np.testing.assert_allclose(data['g2_model'], data['g2_data'], rtol=1.e-4)

    # On this file, no hsm errors
    np.testing.assert_array_equal(data['flag_data'], 0)
    np.testing.assert_array_equal(data['flag_model'], 0)

    image = galsim.fits.read(image_file)
    world = [image.wcs.toWorld(galsim.PositionD(x,y)) for x,y in zip(data['x'],data['y'])]
    np.testing.assert_allclose(data['ra'], [w.ra.deg for w in world], rtol=1.e-4)
    np.testing.assert_allclose(data['dec'], [w.dec.deg for w in world], rtol=1.e-4)

    # Repeat with non-Celestial WCS
    wcs = galsim.AffineTransform(0.26, 0.05, -0.08, -0.24, galsim.PositionD(1024,1024))
    config['input']['wcs'] = wcs
    piff.piffify(config, logger)
    data = fitsio.read(hsm_file)
    np.testing.assert_array_equal(data['ra'], 0.)
    np.testing.assert_array_equal(data['dec'], 0.)
    world = [wcs.toWorld(galsim.PositionD(x,y)) for x,y in zip(data['x'],data['y'])]
    np.testing.assert_allclose(data['u'], [w.x for w in world], rtol=1.e-4)
    np.testing.assert_allclose(data['v'], [w.y for w in world], rtol=1.e-4)

    # Use class directly, rather than through config.
    psf = piff.PSF.read(psf_file)
    stars, _, _ = piff.Input.process(config['input'])
    stars = piff.Select.process(config['select'], stars)
    hsmcat = piff.stats.HSMCatalogStats()
    with np.testing.assert_raises(RuntimeError):
        hsmcat.write('dummy')  # Cannot write before compute
    hsmcat.compute(psf, stars)
    hsm_file2 = os.path.join('output', 'test_hsmcatalog2.fits')
    with np.testing.assert_raises(ValueError):
        hsmcat.write()  # Must supply file_name if not given in constructor
    hsmcat.write(hsm_file2)
    data2 = fitsio.read(hsm_file2)
    for key in data.dtype.names:
        np.testing.assert_allclose(data2[key], data[key], rtol=1.e-5)

@timer
def test_bad_hsm():
    """Test that stats don't break when all stars end up being flagged with hsm errors.
    """
    image_file = os.path.join('input','DECam_00241238_01.fits.fz')
    cat_file = os.path.join('input',
                            'DECam_00241238_01_psfcat_tb_maxmag_17.0_magcut_3.0_findstars.fits')
    psf_file = os.path.join('output','bad_hsm.fits')

    twodhist_file = os.path.join('output','bad_hsm_twod.pdf')
    whisker_file = os.path.join('output','bad_hsm_whisk.pdf')
    rho_file = os.path.join('output','bad_hsm_rho.pdf')
    shape_file = os.path.join('output','bad_hsm_shape.pdf')
    star_file = os.path.join('output','bad_hsm_star.pdf')
    hsm_file = os.path.join('output','bad_hsm_hsm.fits')
    hsm4_file = os.path.join('output','bad_hsm_hsm_fourth.fits')
    sizemag_file = os.path.join('output','bad_hsm_sizemag.png')

    stamp_size = 25

    # The configuration dict with the right input fields for the file we're using.
    config = {
        'input' : {
            'nstars': 8,
            'image_file_name' : image_file,
            'image_hdu' : 1,
            'weight_hdu' : 3,
            'badpix_hdu' : 2,
            'cat_file_name' : cat_file,
            'cat_hdu' : 2,
            # These next two are intentionally backwards.  The PixelGrid will find some kind
            # of solution, but it will be complex garbage, and hsm will fail for them.
            'x_col' : 'YWIN_IMAGE',
            'y_col' : 'XWIN_IMAGE',
            'sky_col' : 'BACKGROUND',
            'stamp_size' : stamp_size,
            'ra' : 'TELRA',
            'dec' : 'TELDEC',
            'gain' : 'GAINA',
        },
        'output' : {
            'file_name' : psf_file,
            'stats' : [
                {
                    'type': 'TwoDHist',
                    'file_name': twodhist_file,
                },
                {
                    'type': 'Whisker',
                    'file_name': whisker_file,
                },
                {  # Note: stats doesn't have to be a list.
                    'type': 'Rho',
                    'file_name': rho_file
                },
                {
                    'type': 'ShapeHist',
                    'file_name': shape_file,
                },
                {
                    'type': 'StarImages',
                    'file_name': star_file,
                },
                {
                    'type': 'StarImages',
                    'file_name': star_file,
                    'include_flagged': True,
                },
                {
                    'type': 'SizeMag',
                    'file_name': sizemag_file,
                },
                {
                    'type': 'HSMCatalog',
                    'file_name': hsm_file,
                },
                {
                    'type': 'HSMCatalog',
                    'file_name': hsm4_file,
                    'fourth_order': True,
                },
            ],
        },
        'psf' : {
            'model' : {
                'type' : 'PixelGrid',
                'scale' : 0.3,
                'size' : 10,
                'interp': 'Lanczos(3)'
            },
            'interp' : { 'type' : 'Mean' },
            'outliers' : {
                'type' : 'Chisq',
                'nsigma' : 0.05   # This will throw out all but 1, which adds an additional
                                  # test of Star stats when nstars < nplot
            }
        },
    }
    if __name__ == '__main__':
        logger = piff.config.setup_logger(1)
    else:
        config['verbose'] = 0
        logger = None

    for f in [twodhist_file, rho_file, shape_file, star_file, hsm_file]:
        if os.path.exists(f):
            os.remove(f)

    piff.piffify(config, logger=logger)

    # Confirm that all but one star was rejected, since that was part of the intent of this test.
    psf = piff.read(psf_file)
    print('stars = ',psf.stars)
    print('flags = ',[s.is_flagged for s in psf.stars])
    print('nremoved = ',psf.nremoved)
    assert len(psf.stars) == 8
    assert np.sum([not s.is_flagged for s in psf.stars]) == 1
    assert psf.nremoved == 7    # There were 8 to start.

    for f in [twodhist_file, rho_file, shape_file, star_file, sizemag_file, hsm_file]:
        assert os.path.exists(f)

    # Check hsm file with bad measurements
    # The one star that was left still fails hsm measurement here.
    data = fitsio.read(hsm_file)
    for col in ['ra', 'dec', 'x', 'y', 'u', 'v',
                'T_data', 'g1_data', 'g2_data',
                'T_model', 'g1_model', 'g2_model',
                'flux', 'reserve', 'flag_data', 'flag_model']:
        assert len(data[col]) == 8
    print('flag_psf = ',data['flag_psf'])
    print('flag_data = ',data['flag_data'])
    print('flag_model = ',data['flag_model'])
    good_index = np.where(data['flag_psf'] == 0)[0]
    np.testing.assert_array_equal(data['flag_data'][good_index], 7)
    np.testing.assert_array_equal(data['flag_model'][good_index], 7)


@timer
def test_base_stats():
    """Test the base Stats class.
    """
    # type is required
    config = { 'file_name' : 'dummy_file' }
    with np.testing.assert_raises(ValueError):
        stats = piff.Stats.process(config)
    # and it must be a valid name
    config['type'] = 'invalid'
    with np.testing.assert_raises(ValueError):
        out = piff.Stats.process(config)

    # ... for all stats in list.
    config = [ { 'type': 'TwoDHist', 'file_name': 'f1' },
               { 'type': 'Whisker', 'file_name': 'f2', },
               { 'type': 'Rho', 'file_name': 'f3' },
               { 'file_name' : 'dummy_file' },
             ]
    with np.testing.assert_raises(ValueError):
        stats = piff.Stats.process(config)

    # Can't do much with a base Stats class
    stats = piff.Stats()
    np.testing.assert_raises(NotImplementedError, stats.compute, None, None)
    np.testing.assert_raises(NotImplementedError, stats.plot)

    # Check that registering new types works correctly
    class NoStats1(piff.Stats):
        pass
    assert NoStats1 not in piff.Stats.valid_stats_types.values()
    class NoStats2(piff.Stats):
        _type_name = None
    assert NoStats2 not in piff.Stats.valid_stats_types.values()
    class ValidStats1(piff.Stats):
        _type_name = 'valid'
    assert ValidStats1 in piff.Stats.valid_stats_types.values()
    assert ValidStats1 == piff.Stats.valid_stats_types['valid']
    with np.testing.assert_raises(ValueError):
        class ValidStats2(piff.Stats):
            _type_name = 'valid'
    with np.testing.assert_raises(ValueError):
        class ValidStats3(ValidStats1):
            pass

@timer
def test_model_properties():
    """Test the model_properties option for hsm catalog.
    """
    # Use PSF with the size a function of color.
    # Note: This test is similar to test_color in test_pixel.py.

    pixel_scale = 0.3
    image = galsim.ImageF(1024,1024, scale=pixel_scale)

    # Draw stars in a grid so we know they don't overlap.
    x_list = []
    y_list = []
    color_list = []
    np_rng = np.random.RandomState(1234)
    rng = galsim.UniformDeviate(1234)
    for x in range(50,1000,100):
        for y in range(50,1000,100):
            # color is random between -1 and +1.
            color = np_rng.uniform(-1,1)
            # Add a +- 1 pixel offset to nominal position.
            xcen = x + np_rng.uniform(-1,1)
            ycen = y + np_rng.uniform(-1,1)
            T = 1.0 + 0.1 * color  # T is linear in color.
            sigma = np.sqrt(T/2)
            star = galsim.Gaussian(sigma=sigma, flux=150.)
            b = galsim.BoundsI(x-16,x+16,y-16,y+16)
            star.drawImage(image=image[b], center=galsim.PositionD(xcen,ycen))
            x_list.append(xcen)
            y_list.append(ycen)
            color_list.append(color)

    noise_sigma = 0.1
    image.addNoise(galsim.GaussianNoise(sigma=noise_sigma, rng=rng))

    # Write out the image and catalog
    image_file = os.path.join('output','hsm_color_image.fits')
    image.write(image_file)
    dtype = [ ('x','f8'), ('y','f8'), ('color','f8') ]
    data = np.empty(len(x_list), dtype=dtype)
    data['x'] = x_list
    data['y'] = y_list
    data['color'] = color_list
    cat_file = os.path.join('output','pixel_color_cat.fits')
    fitsio.write(cat_file, data, clobber=True)

    psf_file = os.path.join('output','hsm_color.piff')
    hsm1_file = os.path.join('output','hsm_color.fits')
    hsm2_file = os.path.join('output','hsm_color_05.fits')
    config = {
        'input' : {
            'image_file_name' : image_file,
            'cat_file_name' : cat_file,
            'x_col' : 'x',
            'y_col' : 'y',
            'property_cols' : ['color'],
            'noise' : noise_sigma**2,
            'stamp_size' : 32,
        },
        'output' : {
            'file_name' : psf_file,
            'stats': [
                {
                    'type': 'HSMCatalog',
                    'file_name': hsm1_file,
                },
                {
                    'type': 'HSMCatalog',
                    'file_name': hsm2_file,
                    'model_properties': {'color' : 0.5},
                },
            ],
        },
        'psf' : {
            'model' : {
                'type' : 'PixelGrid',
                'scale' : pixel_scale,
                'size' : 15
            },
            'interp' : {
                'type' : 'BasisPolynomial',
                'order' : [1, 1, 1],
                'keys': ['u', 'v', 'color'],
            },
        },
    }
    if __name__ == '__main__':
        config['verbose'] = 2
    else:
        config['verbose'] = 0

    piff.piffify(config)
    hsm1 = fitsio.read(hsm1_file)

    # This run measures each star at its own color
    # So there should be no slope in T_data-T_model vs color
    color = hsm1['color']
    T_model = hsm1['T_model']
    T_data = hsm1['T_data']
    m, b = np.polyfit(color, T_data-T_model, 1)
    print()
    print('Not using model_properties:')
    print('dT vs color: m, b = ',m,b)
    assert np.abs(m) < 1.e-3
    assert np.abs(b) < 1.e-3

    # But the raw data does have a significant slope.
    m, b = np.polyfit(color, T_data, 1)
    print('T_data vs color: m, b = ',m,b)
    assert np.abs(m-0.1) < 1.e-3

    # Likewise the model (which follows from the above two tests, but check anyway):
    m, b = np.polyfit(color, T_model, 1)
    print('T_model vs color: m, b = ',m,b)
    assert np.abs(m-0.1) < 1.e-3

    # Check the other output file, which uses model_properties
    hsm2 = fitsio.read(hsm2_file)
    color = hsm2['color']
    T_model = hsm2['T_model']
    T_data = hsm2['T_data']

    # Now the model should all have a size close to T(color=0.5)
    print()
    print('Using model_properties:')
    print('T_model = ',np.mean(T_model),' +- ',np.std(T_model))
    assert np.isclose(np.mean(T_model), 1 + 0.1 * 0.5, rtol=0.02)
    assert np.std(T_model) < 0.005
    m, b = np.polyfit(color, T_model, 1)
    print('T_model vs color: m, b = ',m,b)
    assert np.abs(m) < 2.e-3

    # But the data still covers the whole range
    print('T_data = ',np.mean(T_data),' +- ',np.std(T_data))
    assert np.isclose(np.mean(T_data), 1, rtol=0.03)
    assert np.std(T_data) > 0.05
    m, b = np.polyfit(color, T_data, 1)
    print('T_data vs color: m, b = ',m,b)
    assert np.abs(m-0.1) < 2.e-3

    # Finally, T_data - T_model  should show the input slope of 0.1
    m, b = np.polyfit(color, T_data-T_model, 1)
    print('dT vs color: m, b = ',m,b)
    assert np.abs(m-0.1) < 2.e-3

@timer
def test_fourth_order():
    """Test HSMCatalog with fourth_order=True
    """
    if __name__ == '__main__':
        logger = piff.config.setup_logger(verbose=2)
    else:
        logger = piff.config.setup_logger(log_file='output/test_hsmcatalog.log')

    image_file = os.path.join('output','test_stats_image.fits')
    cat_file = os.path.join('output','test_stats_cat.fits')
    psf_file = os.path.join('output','test_starstats.fits')
    hsm_file = os.path.join('output', 'test_hsmcatalog.fits')
    config = {
        'input' : {
            'image_file_name' : image_file,
            'cat_file_name' : cat_file,
            'stamp_size' : 48,
        },
        'psf' : {
            'model' : { 'type' : 'Gaussian',
                        'fastfit': True,
                        'include_pixel': False },
            'interp' : { 'type' : 'Mean' },
        },
        'output' : {
            'file_name' : psf_file,
            'stats' : [
                {
                    'type': 'HSMCatalog',
                    'file_name': hsm_file,
                    'fourth_order': True
                }
            ]
        }
    }
    piff.piffify(config, logger)
    assert os.path.isfile(hsm_file)

    data = fitsio.read(hsm_file)
    print('data = ',data)
    # Check that the model and data measurements are close
    np.testing.assert_allclose(data['T_model'], data['T_data'], rtol=1.e-4)
    np.testing.assert_allclose(data['g1_model'], data['g1_data'], rtol=1.e-4)
    np.testing.assert_allclose(data['g2_model'], data['g2_data'], rtol=1.e-4)
    np.testing.assert_allclose(data['T4_model'], data['T4_data'], rtol=1.e-4)
    np.testing.assert_allclose(data['g41_model'], data['g41_data'], atol=1.e-4)
    np.testing.assert_allclose(data['g42_model'], data['g42_data'], atol=1.e-4)
    np.testing.assert_allclose(data['h41_model'], data['h41_data'], rtol=1.e-4)
    np.testing.assert_allclose(data['h42_model'], data['h42_data'], rtol=1.e-4)

    # Check that the moment values are what we intend them to be
    psf = piff.read(psf_file)
    stars = piff.Star.load_images(psf.stars, image_file)
    for i, star in enumerate(stars):
        moments = piff.util.calculate_moments(star, fourth_order=True)
        T = moments['M11']*2
        shape = galsim.Shear(e1=moments['M20']/moments['M11'],
                             e2=moments['M02']/moments['M11'])
        print('moments = ',moments)
        print('hsm = ',star.hsm)
        print('data = ',data[i])
        print(data['T_data'][i], T, 2*star.hsm[3]**2 / (1-shape.e**2)**0.5)
        print(data['g1_data'][i], shape.g1, star.hsm[4])
        print(data['g2_data'][i], shape.g2, star.hsm[5])
        np.testing.assert_allclose(data['T_data'][i], T, rtol=1.e-5)
        np.testing.assert_allclose(data['g1_data'][i], shape.g1, rtol=1.e-5)
        np.testing.assert_allclose(data['g2_data'][i], shape.g2, rtol=1.e-5)
        T4 = moments['M22'] / T
        np.testing.assert_allclose(data['T4_data'][i], moments['M22']/moments['M11'], rtol=1.e-5)
        np.testing.assert_allclose(data['g41_data'][i],
                                   moments['M31']/moments['M11']**2 - 3*shape.e1, atol=1.e-5)
        np.testing.assert_allclose(data['g42_data'][i],
                                   moments['M13']/moments['M11']**2 - 3*shape.e2, atol=1.e-5)
        np.testing.assert_allclose(data['h41_data'][i],
                                   moments['M40']/moments['M11']**2, rtol=1.e-5)
        np.testing.assert_allclose(data['h42_data'][i],
                                   moments['M04']/moments['M11']**2, rtol=1.e-5)

        # Our simulated data here are elliptical Gaussians, so check that the fourth order terms
        # match what we expect for them.
        #
        # First, for a round Gaussian, M22 = T^2.
        # When there is some ellipticity, there is a correction of (1-e^2).
        # It doesn't come out exact, but it's reasonably close.  Not sure why it's not closer...
        print('T4: ', data['T4_data'][i], T/(1-shape.e**2)**0.5)
        np.testing.assert_allclose(data['T4_data'][i], T/(1-shape.e**2)**0.5, rtol=0.05)

        # Next, the naive 4th order shape of an elliptical Gaussian is approximately 3e:
        # M31/M11^2 ~= 3 M20/M11
        # M13/M11^2 ~= 3 M02/M11
        print('e4: ', moments['M31']/moments['M11']**2, 3*moments['M20']/moments['M11'])
        print('e4: ', moments['M13']/moments['M11']**2, 3*moments['M02']/moments['M11'])
        np.testing.assert_allclose(moments['M31']/moments['M11'], 3*moments['M20'], rtol=1.e-3)
        np.testing.assert_allclose(moments['M13']/moments['M11'], 3*moments['M02'], rtol=1.e-3)
        # Our g4 measurements subtract off this leading order effect, so for these Gaussian
        # profiles, the 4th order terms are close to 0.
        print('g4: ', data['g41_data'][i], data['g42_data'][i])
        np.testing.assert_allclose(data['g41_data'][i], 0, atol=1.e-3)
        np.testing.assert_allclose(data['g42_data'][i], 0, atol=1.e-3)

        # I didn't try to figure out what the spin-4 values should be for a Gaussian.
        # If someone wants to work that out, it would be nice to add a test that they are right.
        # Empirically, it seems to come out pretty close to 10 x (g1+i g2)^2.
        # The g^2 bit makes sense, but I can't figure out where the factor of ~10 comes from.
        print('h4: ', data['h41_data'][i], data['h42_data'][i])

    # Repeat, adding in raw_moments
    config['output']['stats'][0]['raw_moments'] = True
    piff.piffify(config, logger)
    data = fitsio.read(hsm_file)

    # Check that the model and data measurements are close
    for name in ('T', 'g1', 'g2', 'T4', 'h41', 'h42',
                 'M00', 'M10', 'M01', 'M11', 'M20', 'M02',
                 'M22', 'M31', 'M13', 'M40', 'M04',
                 'M22n', 'M33n', 'M44n'):
        np.testing.assert_allclose(data[name+'_model'], data[name+'_data'], rtol=1.e-4)
    for name in ('g41', 'g42', 'M21', 'M12', 'M30', 'M03'):
        # These are close to 0, so use atol, not rtol.
        np.testing.assert_allclose(data[name+'_model'], data[name+'_data'], atol=1.e-4)

    # Check that the moment values are what we intend them to be
    for i, star in enumerate(stars):
        moments = piff.util.calculate_moments(star, third_order=True, fourth_order=True,
                                              radial=True)
        # Repeat the tests from above to ensure that raw_moments=True doesn't mess up the
        # fourth_order=True measurements.
        T = moments['M11']*2
        shape = galsim.Shear(e1=moments['M20']/moments['M11'],
                             e2=moments['M02']/moments['M11'])
        np.testing.assert_allclose(data['T_data'][i], T, rtol=1.e-5)
        np.testing.assert_allclose(data['g1_data'][i], shape.g1, rtol=1.e-5)
        np.testing.assert_allclose(data['g2_data'][i], shape.g2, rtol=1.e-5)
        T4 = moments['M22'] / T
        np.testing.assert_allclose(data['T4_data'][i], moments['M22']/moments['M11'], rtol=1.e-5)
        np.testing.assert_allclose(data['g41_data'][i],
                                   moments['M31']/moments['M11']**2 - 3*shape.e1, atol=1.e-5)
        np.testing.assert_allclose(data['g42_data'][i],
                                   moments['M13']/moments['M11']**2 - 3*shape.e2, atol=1.e-5)
        np.testing.assert_allclose(data['h41_data'][i],
                                   moments['M40']/moments['M11']**2, rtol=1.e-5)
        np.testing.assert_allclose(data['h42_data'][i],
                                   moments['M04']/moments['M11']**2, rtol=1.e-5)
        np.testing.assert_allclose(data['T4_data'][i], T/(1-shape.e**2)**0.5, rtol=0.05)
        np.testing.assert_allclose(moments['M31']/moments['M11'], 3*moments['M20'], rtol=1.e-3)
        np.testing.assert_allclose(moments['M13']/moments['M11'], 3*moments['M02'], rtol=1.e-3)
        np.testing.assert_allclose(data['g41_data'][i], 0, atol=1.e-3)
        np.testing.assert_allclose(data['g42_data'][i], 0, atol=1.e-3)

        for name in moments.keys():
            # These should be exactly the same.
            np.testing.assert_allclose(data[name+'_data'][i], moments[name])
            # And the model ones should be close.
            np.testing.assert_allclose(data[name+'_model'][i], moments[name], atol=1.e-4)

    # Finally make sure raw_moments works without fourth_order=True
    del config['output']['stats'][0]['fourth_order']
    piff.piffify(config, logger)
    data = fitsio.read(hsm_file)
    for i, star in enumerate(stars):
        moments = piff.util.calculate_moments(star, third_order=True, fourth_order=True,
                                              radial=True)
        for name in moments.keys():
            # These should be exactly the same.
            np.testing.assert_allclose(data[name+'_data'][i], moments[name])
            # And the model ones should be close.
            np.testing.assert_allclose(data[name+'_model'][i], moments[name], atol=1.e-4)


@timer
def test_property_cols():
    """Test that extra property_cols get output correctly in the hsm output file.
    """
    image_file = 'input/D00572501_z_c01_r3624p01_immasked.fits.fz'
    cat_file = 'input/D00572501_z_c01_r5473p01_piff.fits'
    psf_file = os.path.join('output','test_property_cols.piff')
    hsm_file = os.path.join('output','test_property_cols_hsm.fits')

    nstars = 25
    scale = 0.26
    size = 15
    order = 1
    stamp_size = 25

    config = {
        'input' : {
            'nstars': nstars,
            'image_file_name' : image_file,
            'image_hdu' : 1,
            'weight_hdu' : 3,
            'badpix_hdu' : 2,
            'cat_file_name' : cat_file,
            'x_col' : 'XWIN_IMAGE',
            'y_col' : 'YWIN_IMAGE',
            'sky_col' : 'BACKGROUND',
            'stamp_size' : stamp_size,
            'ra' : 'TELRA',
            'dec' : 'TELDEC',
            'gain' : 'GAINA',
            'satur' : 'SATURATA',
            'chipnum': 1,
            # Select ones with a variety of dtypes.
            'property_cols' : ['SOURCE_ID', 'GI_COLOR', 'FLAGS', 'FLAG_COLOR', 'SPREAD_MODEL'],
        },
        'select' : {
            'type': 'Properties',
            'where': 'np.abs(SPREAD_MODEL) < 3.e-4',

            'reserve_frac' : 0.2,
            'seed' : 1234,
        },
        'psf' : {
            'model' : {
                'type' : 'PixelGrid',
                'scale' : scale,
                'size' : size,
                'interp' : 'Lanczos(5)',
            },
            'interp' : {
                'type' : 'BasisPolynomial',
                'order' : [1, 1, 1],
                'keys': ['u', 'v', 'GI_COLOR'],
            },
        },
        'output' : {
            'file_name' : psf_file,
            'stats': [
                {
                    'type': 'HSMCatalog',
                    'file_name': hsm_file,
                },
            ],
        },
    }

    piff.piffify(config)
    hsm = fitsio.read(hsm_file)
    cat = fitsio.read(cat_file)

    print('hsm dtype = ',hsm.dtype)
    print('cat dtype = ',cat.dtype)

    for key in hsm.dtype.names:
        print(key)
        if key in cat.dtype.names:
            assert hsm[key].dtype.type == cat[key].dtype.type
        elif key == 'reserve':
            assert hsm[key].dtype.type == np.dtype(bool).type
        elif key.startswith('flag'):
            assert hsm[key].dtype.type == np.dtype(int).type
        elif key == 'sky':
            # This one is read from the input catalog, but renamed
            assert hsm[key].dtype.type == np.float32
        else:
            assert hsm[key].dtype.type == np.dtype(float).type

    # Check that drawing the image works without specifying chipnum.
    # This is ok so long as the input is really only a single chip.
    # cf. Issue #140
    psf = piff.read(psf_file)
    im1 = psf.draw(35, 40, center=True, GI_COLOR=1)

    # If the input field didn't include chipnum, then it makes no difference for a single chip.
    del config['input']['chipnum']
    piff.piffify(config)
    psf = piff.read(psf_file)
    im2 = psf.draw(35, 40, center=True, GI_COLOR=1)
    assert im1 == im2


if __name__ == '__main__':
    setup()
    test_twodstats()
    test_shift_cmap()
    test_twodstats_config()
    test_rhostats_config()
    test_shapestats_config()
    test_starstats_config()
    test_hsmcatalog()
    test_bad_hsm()
    test_base_stats()
    test_model_properties()
    test_fourth_order()
    test_property_cols()
