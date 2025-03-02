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

"""
.. module:: pixelmodel
"""

import numpy as np
import galsim
import scipy.linalg
import warnings

from galsim import Lanczos
from .model import Model
from .star import Star

class PixelGrid(Model):
    """A PSF modeled as interpolation between a grid of points.

    The parameters of the model are the values at the grid points, although the sum of the
    values is constrained to be 1/scale**2, to give it unit total flux. The grid is in uv
    space, with the scale and size specified on construction.  Interpolation will always
    assume values of zero outside of grid.

    PixelGrid also needs to specify an interpolant to define how to values between grid points
    are determined from the pixelated model.  Any galsim.Interpolant type is allowed.
    The default interpolant is galsim.Lanczos(7)

    The following initialization methods are available for the ``init`` parameter.

    * hsm           Start with flux and size values that match the hsm moments of the star.
    * zero          Start with flux = 1.e-6 x the hsm flux.
    * delta         Start with size = 1.e-6 x the hsm size.

    All initialization methods start with zero shear and zero centroid offset.

    Use type name "PixelGrid" in a config field to use this model.

    :param scale:       Pixel scale of the PSF model (in arcsec)
    :param size:        Number of pixels on each side of square grid.
    :param interp:      An Interpolant to be used [default: Lanczos(7)]
    :param centered:    If True, PSF model centroid is forced to be (0,0), and the
                        PSF fitting will marginalize over stellar position.  If False, stellar
                        position is fixed at input value and the fitted PSF may be off-center.
                        [default: True]
    :param init:        Initialization method.  [default: None, which uses hsm unless a PSF
                        class specifies a different default.]
    :param fit_flux:    If True, the PSF model will include the flux value.  This is useful when
                        this model is an element of a Sum composite PSF. [default: False]
    :param logger:      A logger object for logging debug info. [default: None]
    """

    _type_name = 'PixelGrid'
    _method = 'no_pixel'
    _model_can_be_offset = True  # Indicate that in reflux, the centroid should also move by the
                                 # current centroid of the model.  This way on later iterations,
                                 # the model will be close to centered.

    def __init__(self, scale, size, interp=None, centered=True, init=None, fit_flux=False,
                 logger=None):

        logger = galsim.config.LoggerWrapper(logger)
        logger.debug("Building Pixel model with the following parameters:")
        logger.debug("scale = %s",scale)
        logger.debug("size = %s",size)
        logger.debug("interp = %s",interp)
        logger.debug("centered = %s",centered)
        logger.debug("init = %s",init)
        logger.debug("fit_flux = %s",fit_flux)

        self.scale = scale
        self.size = size
        self.pixel_area = self.scale*self.scale
        if interp is None: interp = Lanczos(7)
        elif isinstance(interp, str): interp = eval(interp)
        self.interp = interp
        self._centered = centered
        self._init = init
        self._fit_flux = fit_flux

        # We will limit the calculations to |u|, |v| <= maxuv
        self.maxuv = (self.size+1)/2. * self.scale

        # The origin of the model in image coordinates
        # (Same for both u and v directions.)
        self._origin = self.size//2

        # These are the kwargs that can be serialized easily.
        self.kwargs = {
            'scale' : scale,
            'size' : size,
            'centered' : centered,
            'interp' : repr(self.interp),
            'init': init,
            'fit_flux': fit_flux,
        }
        self.set_num(None)

        if size <= 0:
            raise ValueError("Non-positive PixelGrid size {:d}".format(size))

        self._nparams = size*size
        logger.debug("nparams = %d",self._nparams)

    def initialize(self, star, logger=None, default_init=None):
        """Initialize a star to work with the current model.

        :param star:            The Star to initialize.
        :param logger:          A logger object for logging debug info. [default: None]
        :param default_init:    The default initilization method if the user doesn't specify one.
                                [default: None]

        :returns: a star instance with the appropriate initial fit values
        """
        logger = galsim.config.LoggerWrapper(logger)
        init = self._init if self._init is not None else default_init
        if init is None: init = 'hsm'
        logger.debug("initializing PixelGrid with method %s",init)

        if init == 'hsm' or init == 'zero':
            # Calculate the second moment to initialize an initial Gaussian profile.
            # hsm returns: flux, x, y, sigma, g1, g2, flag
            sigma = star.hsm[3]

            # Create an initial parameter array using a Gaussian profile.
            u = np.arange( -self._origin, self.size-self._origin) * self.scale
            v = np.arange( -self._origin, self.size-self._origin) * self.scale
            rsq = (u*u)[:,np.newaxis] + (v*v)[np.newaxis,:]
            gauss = np.exp(-rsq / (2.* sigma**2))
            params = gauss.ravel()

            # Normalize to get unity flux
            params /= np.sum(params)

            if init == 'zero':
                # Setting to exactly 0 doesn't work, since InterpolatedImages need to have a
                # valid flux.  But 1.e-10 x smaller than the image should be a good starting
                # point for most uses of the zero initialization.
                params *= 1.e-10

        elif init == 'delta':
            params = np.zeros(self.size**2)
            icenter = self._origin * self.size + self._origin
            params[icenter] = 1.0

        else:
            raise ValueError("init = %s is invalid for PixelGrid"%init)

        fit = star.fit.newParams(params=params, num=self._num)
        return Star(star.data, fit)

    def fit(self, star, logger=None, convert_func=None, draw_method=None):
        """Fit the Model to the star's data to yield iterative improvement on its PSF parameters
        and uncertainties.

        :param star:            A Star instance
        :param logger:          A logger object for logging debug info. [default: None]
        :param convert_func:    An optional function to apply to the profile being fit before
                                drawing it onto the image.  This is used by composite PSFs to
                                isolate the effect of just this model component. [default: None]
        :param draw_method:     The method to use with the GalSim drawImage command to determine
                                the residuals. [PixelGrid always uses 'no_pixel'; this parameter
                                is only present for API compatibility.  It must be either None
                                or 'no_pixel'.]

        :returns: a new Star instance with updated fit information
        """
        assert draw_method in (None, 'no_pixel')
        logger = galsim.config.LoggerWrapper(logger)
        # Get chisq Taylor expansion for linearized model
        star1 = self.chisq(star, logger=logger, convert_func=convert_func)

        # The chisq function calculates A and b where
        #
        #    chisq = chisq_0 + 2 bT A dp + dpT AT A dp
        #
        # is the linearized variation in chisq with respect to changes in the parameter values.
        # The minimum of this linearized functional form is
        #
        #    dp = (AT A)^-1 AT b
        #
        # This is just the least squares solution of
        #
        #    A dp = b
        #
        # Even if the solution is degenerate, gelsy works fine using QRP decomposition.
        # And it's much faster than SVD.
        dparam = scipy.linalg.lstsq(star1.fit.A, star1.fit.b,
                                    check_finite=False, cond=1.e-6,
                                    lapack_driver='gelsy')[0]
        logger.debug('dparam = %s',dparam)

        # Create new StarFit, update the chisq value.  Note no beta is returned as
        # the quadratic Taylor expansion was about the old parameters, not these.
        Adp = star1.fit.A.dot(dparam)
        new_chisq = star1.fit.chisq + Adp.dot(Adp) - 2 * Adp.dot(star1.fit.b)
        logger.debug('chisq = %s',new_chisq)

        # covariance of dp is C = (AT A)^-1
        # params_var = diag(C)
        try:
            params_var = np.diagonal(scipy.linalg.inv(star1.fit.A.T.dot(star1.fit.A)))
        except np.linalg.LinAlgError as e:
            # If we get an error, set the variance to "infinity".
            logger.info("Caught error %s making params_var.  Setting all to 1.e100",e)
            params_var = np.ones_like(dparam) * 1.e100

        params = star.fit.get_params(self._num)
        params += dparam
        star = Star(star1.data, star1.fit.newParams(params=params, params_var=params_var,
                                                    num=self._num, chisq=new_chisq))
        self.normalize(star)
        return star

    def chisq(self, star, logger=None, convert_func=None, draw_method=None):
        """Calculate dependence of chi^2 = -2 log L(D|p) on PSF parameters for single star.
        as a quadratic form chi^2 = dp^T AT A dp - 2 bT A dp + chisq,
        where dp is the *shift* from current parameter values.  Returned Star
        instance has the resultant (A, b, chisq) attributes, but params vector has not have
        been updated yet (could be degenerate).

        :param star:            A Star instance
        :param logger:          A logger object for logging debug info. [default: None]
        :param convert_func:    An optional function to apply to the profile being fit before
                                drawing it onto the image.  This is used by composite PSFs to
                                isolate the effect of just this model component. [default: None]
        :param draw_method:     The method to use with the GalSim drawImage command to determine
                                the residuals. [PixelGrid always uses 'no_pixel'; this parameter
                                is only present for API compatibility.  It must be either None
                                or 'no_pixel'.]

        :returns: a new Star instance with updated fit parameters. (esp. A,b)
        """
        assert draw_method in (None, 'no_pixel')
        logger = galsim.config.LoggerWrapper(logger)
        logger.debug('Start chisq function')
        logger.debug('initial params = %s',star.fit.get_params(self._num))

        data, weight, u, v = star.data.getDataVector()
        prof = self.getProfile(star.fit.get_params(self._num))._shift(*star.fit.center)
        logger.debug('prof.flux = %s',prof.flux)

        # My idea for doing composite functions is that at this point in the calculation, we
        # could apply a function to prof to convert it to the full effective PSF profile.
        # This function could be passed as an optional extra argument to the fit and chisq
        # functions.  (The default would just be `lambda prof:prof`.)
        # E.g. in a Sum context, this function could be
        #    convert_func = `lambda prof: galsim.Sum(prof, *other_profiles)`
        # Then at this point in the chisq function (and comparable places for other profiles),
        # we would call:
        #    prof = convert_func(prof)
        # The draw function below would then draw the full composite profile, not just the
        # PixelGrid profile.

        if convert_func is not None:
            prof = convert_func(prof)
            logger.debug(f'converted prof = {prof}')

        # Adjust the image now so that we can draw it in pixel coordinates, rather than letting
        # galsim.drawImage do the adjustment each time for each component, which would be
        # incredibly slow.
        image = star.image.copy()
        offset = prof._adjust_offset(image.bounds, galsim.PositionD(0,0), star.image_pos, False)
        image._shift(-image.center)
        image.wcs = galsim.PixelScale(1.0)

        # Draw the profile.
        prof = star.data.local_wcs.profileToImage(prof, offset=offset)
        if (convert_func is None or
                (prof.is_analytic_x and not isinstance(prof, galsim.Convolution))):
            draw_real = True
            prof._drawReal(image)
        else:
            # If the convert func turns this into a Convolution, or something else that isn't
            # analytic in real space, then use FFT drawing.
            draw_real = False
            prof.drawFFT(image)
        logger.debug('drawn flux = %s',image.array.sum())
        model = image.array.ravel() * star.fit.flux

        # Only use data points where model gives reasonable support
        u0, v0 = star.fit.center
        u -= u0
        v -= v0
        mask = (np.abs(u) <= self.maxuv) & (np.abs(v) <= self.maxuv) & (weight != 0)
        nmask = np.sum(mask)
        data = data[mask]
        model = model[mask]
        weight = weight[mask]

        # Calculate A = d(model)/dp
        # A[i,k] = d(model_i)/dp_k
        # b[i] = resid_i
        # Solution to A x = b will be the desired dparams
        A = np.zeros((nmask, self._nparams), dtype=float, order='F')
        b = data - model

        # The PixelGrid model basis can be represented as a 1x1 InterpolatedImage with flux=1,
        # shifted and scaled appropriately.  The _getBasisProfile method returns a single
        # InterpolatedImage we can use for all the pixels, with arrays of shifts (du,dv) to use
        # for each of the individual pixels.
        basis_profile, basis_shifts = self._getBasisProfile()
        du, dv = basis_shifts

        if convert_func is not None:
            # In this case we need the basis_profile to have the right scale (rather than
            # incorporate it into the jacobian) so that convert_func will have the right size.
            basis_profile = basis_profile.dilate(self.scale)
            logger.debug(f'basis_profile = {basis_profile}')
            # Find the net shift from the star.fit.center and the offset.
            jac = star.data.local_wcs.jacobian().inverse().getMatrix()
            jac_det = abs(jac[0,0]*jac[1,1] - jac[0,1]*jac[1,0])
            dx = jac[0,0]*u0 + jac[0,1]*v0 + offset.x
            dy = jac[1,0]*u0 + jac[1,1]*v0 + offset.y
            du = du.ravel() * self.scale
            dv = dv.ravel() * self.scale
            for k, duk, dvk in zip(range(self._nparams), du,dv):
                prof = basis_profile._shift(duk,dvk)
                prof = convert_func(prof)
                if draw_real:
                    prof._drawReal(image, jac, (dx,dy), 1.)
                    # Equivalent to:
                    #prof = galsim._Transform(prof, jac, (dx,dy), 1./jac_det)
                    #prof.drawReal(image)
                else:
                    prof = galsim._Transform(prof, jac, (dx,dy), 1./jac_det)
                    prof.drawFFT(image)
                A[:,k] = image.array.ravel()[mask]
        else:
            if 0:
                # When we don't have the convert_func step, this calculation can be sped up
                # fairly significantly.  If we wanted to use only GalSim method, then this is
                # how we would do it.  We can combine both the scale and the initial shift
                # into the parameters that we pass to _drawReal, which saves time.
                # This is reasonably straightforward.  However, when we don't have any convert
                # function, there is a further speed up that is available to us by using the
                # fact that each kernel weight value is used multiple times for different
                # output pixels.  GalSim uses this fact when drawing the full PixelGrid model,
                # but there's no way to get that efficiency gain when doing one model pixel at
                # a time.  So we do the equivalent calculation below, outside of GalSim.

                jac = star.data.local_wcs.jacobian().inverse().getMatrix()
                # Incorporate scale into jac for _drawReal call.
                # Also for the du = du * scale and dv = dv * scale steps.
                jac2 = jac * self.scale
                dx = jac2[0,0]*du.ravel() + jac2[0,1]*dv.ravel()
                dx += jac[0,0]*u0 + jac[0,1]*v0 + offset.x
                dy = jac2[1,0]*du.ravel() + jac2[1,1]*dv.ravel()
                dy += jac[1,0]*u0 + jac[1,1]*v0 + offset.y

                for k, dxk, dyk in zip(range(self._nparams), dx,dy):
                    basis_profile._drawReal(image, jac2, (dxk,dyk), 1.)
                    A[:,k] = image.array.ravel()[mask]
            else:
                # This is even faster, but less easy to follow how it works.
                # I'll make an attempt to explain how it proceeds, but I find it somewhat
                # more confusing than the above method.

                # Note: The main reason this is faster is that we only compute the interpolation
                # xvals for npix * (2*xr) * 2, rather than npix * (2*xr)**2 by leveraging
                # the fact that each interpolation coefficient gets repeated for multiple
                # basis pixels, so the above drawReal call has duplicated work, which cannot
                # really be pulled out into a common calculation using just GalSim functionality.

                # First calculate the interp.xval values that we will need.
                # We need to evaluate the interpolation coefficient using self.interp.xvale
                # at any integer multiples of self.scale that are sufficiently near u or v.
                # More simply, we need to evaluate at integer locations that are near u/scale
                # or v/scale.  The argument to xval needs to be the distance this integer location
                # is from u or v.
                # The maximum argument is given by self.interp.xrange.
                u = u[mask] / self.scale
                v = v[mask] / self.scale
                ui,uf = np.divmod(u,1)
                vi,vf = np.divmod(v,1)
                xr = int(np.ceil(self.interp.xrange))
                # Note arguments are basis pixel position minus image pixel position.
                # Hence the minus sign in front of uf.
                argu = -uf[:,np.newaxis] + np.arange(-xr+1,xr+1)[np.newaxis,:]
                argv = -vf[:,np.newaxis] + np.arange(-xr+1,xr+1)[np.newaxis,:]
                uwt = self.interp.xval(argu.ravel()).reshape(argu.shape)
                vwt = self.interp.xval(argv.ravel()).reshape(argv.shape)

                # The interpolation coefficients are uwt * vwt * flux_ratio
                # We need one factor the pixel area ratio so arbitratily choose uwt to
                # multiply by this (constant) factor so it gets applied to the product.
                flux_scaling = star.data.pixel_area / self.pixel_area
                uwt *= flux_scaling

                # Now the tricky part.  We need to figure out which basis pixel each of those
                # combinations belongs to.
                # This is easier to do if we don't loop over basis pixels as we did above, but
                # rather loop over the image pixels.  Then we can fill the appropriate columns
                # in the A matrix for each row.
                # For each row, the columns we need are those with
                #   int(u) - xrange + 1 <= du < int(u) + xrange + 1
                #   int(v) - xrange + 1 <= dv < int(v) + xrange + 1
                # We can figure this out by slicing into an array that has the same shape
                # as du or dv with the running index indicating which basis pixel corresponds
                # to each location.
                ui = ui.astype(int)
                vi = vi.astype(int)
                col_index = np.arange(self._nparams).reshape(du.shape)

                # For each row, we need the outer product of uwt and vwt.
                # Not the whole thing all the time, but despite that, it's faster to
                # have numpy do this product all at once in a single C call rather than
                # separately for each row.
                uvwt = uwt[:, np.newaxis, :] * vwt[:, :, np.newaxis]

                for i in range(nmask):
                    # i1:i2 is the slice for the v direction into the col_index array.
                    # p1:p2 is the slice for the v direction into the uwt array.
                    # Normally p1:p2 is just 0:2*xr, but we need to be careful about going
                    # off the edge of the grid, so it may be smaller than this.
                    i1 = vi[i] - xr + self._origin + 1
                    i2 = vi[i] + xr + self._origin + 1
                    p1 = 0
                    p2 = 2*xr
                    if i1 < 0:
                        p1 = -i1
                        i1 = 0
                    if i2 > self.size:
                        p2 -= i2 - self.size
                        i2 = self.size
                    # Repeat for u using j1:j2 and q1:q2
                    j1 = ui[i] - xr + self._origin + 1
                    j2 = ui[i] + xr + self._origin + 1
                    q1 = 0
                    q2 = 2*xr
                    if j1 < 0:
                        q1 = -j1
                        j1 = 0
                    if j2 > self.size:
                        q2 -= j2 - self.size
                        j2 = self.size

                    # Now we have the right indices for everything
                    # i1:i2 are the v indices in the col_index array.
                    # j1:j2 are the u indices in the col_index array.
                    # p1:p2 are the v indices to use
                    # q1:q2 are the u indices to use
                    # The interpolation coefficients are the outer product of these.
                    # cols are the indices of the corresponding basis pixels.
                    cols = col_index[i1:i2, j1:j2]
                    A[i, cols.ravel()] = uvwt[i, p1:p2, q1:q2].ravel()

        # Account for the current flux estimate.
        A *= star.fit.flux

        # Actually, do weighted least squares.
        # Multiply A and b by sqrt(weight).
        sw = np.sqrt(weight)
        A *= sw[:,np.newaxis]
        b *= sw
        chisq = np.sum(b**2)
        dof = np.count_nonzero(weight)
        logger.debug('chisq,dof = %s,%s',chisq,dof)

        return Star(star.data, star.fit.withNew(chisq=chisq, dof=dof, A=A, b=b))

    def getProfile(self, params):
        """Get a version of the model as a GalSim GSObject

        :param params:      The fit parameters for a given star.

        :returns: a galsim.GSObject instance
        """
        im = galsim.Image(params.reshape(self.size,self.size), scale=self.scale)
        flux = None if self._fit_flux else 1.
        return galsim.InterpolatedImage(im, x_interpolant=self.interp,
                                        use_true_center=False, flux=flux)

    def _getBasisProfile(self):
        if not hasattr(self, '_basis_profile'):
            self._basis_profile = []
            # Note: Things are faster if the underlying InterpolatedImage has scale=1.
            # We apply the dilation and shifts separately in chisq2.
            im = galsim.Image(np.array([[1.]]), scale=1.)
            self._basis_profile = galsim.InterpolatedImage(im, x_interpolant=self.interp)

            self._basis_shifts = np.meshgrid(
                np.arange(-self._origin, -self._origin+self.size),
                np.arange(-self._origin, -self._origin+self.size))

        return self._basis_profile, self._basis_shifts

    def normalize(self, star):
        """Make sure star.fit.params are normalized properly.

        Note: This modifies the input star in place.
        """
        # Backwards compatibility check.
        # We used to only keep nparams - 1 or nparams - 3 values in fit.params.
        # If this is the case, fix it up to match up with our new convention.
        params = star.fit.get_params(self._num)
        nparams1 = len(params)
        nparams2 = self.size**2
        if nparams1 < nparams2:
            # Difference is either 1 or 3.  If not, something very weird happened.
            assert nparams2 - nparams1 in [1,3]

            # First copy over the parameters into the full array
            temp = np.zeros((self.size,self.size))
            mask = np.ones((self.size,self.size), dtype=bool)
            origin = (self.size//2, self.size//2)
            mask[origin] = False
            if nparams2 == nparams1 + 3:  # pragma: no branch
                # Note: the only regression we test is with centroids free, so we always hit
                #       this branch.
                mask[origin[0]+1,origin[1]] = False
                mask[origin[0],origin[1]+1] = False
            temp[mask] = params

            # Now populate the masked pixels
            delta_u = np.arange(-origin[0], self.size-origin[0])
            delta_v = np.arange(-origin[1], self.size-origin[1])
            u, v = np.meshgrid(delta_u, delta_v)
            if nparams2 == nparams1 + 3:  # pragma: no branch
                # Do off-origin pixels first so that the centroid is 0,0.
                temp[origin[0]+1, origin[1]] = -np.sum(v*temp)
                temp[origin[0], origin[1]+1] = -np.sum(u*temp)

            # Now the center from the total flux == 1
            # Note: This uses the old scheme of sb normalization, not flux normalization.
            temp[origin] = 1./self.pixel_area - np.sum(temp)

            params = temp.flatten()
            star.fit.params = None  # Remove the old one with the wrong size, so newParams
                                    # doesn't complain about the size changing.

        # Normally this is all that is required.
        if not self._fit_flux:
            params /= np.sum(params)
            star.fit = star.fit.newParams(params, num=self._num)

    @classmethod
    def _fix_kwargs(cls, kwargs):
        # Old (v1.0 and earlier) versions included two parameters that are now obsoloete.
        # Remove them if they are present.
        kwargs.pop('degenerate', None)
        kwargs.pop('start_sigma', None)

        # Some (even older -- v0.2.x) files don't include the interp.  The default back then
        # was Lanczos(3), so if it's not present, set it to that.
        if 'interp' not in kwargs:
            kwargs['interp'] = galsim.Lanczos(3)
