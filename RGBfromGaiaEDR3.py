# -*- coding: utf-8 -*-
#
# Copyright 2021 Universidad Complutense de Madrid
#
# SPDX-License-Identifier: GPL-3.0+
# License-Filename: LICENSE.txt
#

"""
RGB predictions of Gaia EDR3 stars

This code is hosted at https://github.com/nicocardiel/RGBfromGaiaEDR3
Maintainer: Nicolás Cardiel <cardiel@ucm.es>

Usage example:
$ python RGBfromGaiaEDR3.py 56.66 24.10 1.0 12
"""

import argparse
from astropy import units as u
from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.table import Column
from astropy.wcs import WCS
from astroquery.gaia import Gaia
import glob
import matplotlib.pyplot as plt
import matplotlib as mpl
mpl.rcParams['font.size'] = 17.0
mpl.rcParams['font.family'] = 'serif'
mpl.rcParams['axes.linewidth'] = 2
import numpy as np
from numpy.polynomial import Polynomial
import os
import sys
import urllib

MAX_SEARCH_RADIUS = 30  # degrees
EDR3_SOURCE_ID_15M_ALLSKY = 'edr3_source_id_15M_allsky.fits'
EDR3_SOURCE_ID_PARAMS_15M_ALLSKY = 'edr3_source_id_params_15M_allsky.fits'
RGB_FROM_GAIA_ALLSKY = 'rgb_from_gaia_allsky.fits'
VERSION = 1.0


def main():

    parser = argparse.ArgumentParser(description="RGB predictions for Gaia EDR3 stars")
    parser.add_argument("ra_center", help="right Ascension (decimal degrees)", type=float)
    parser.add_argument("dec_center", help="declination (decimal degrees)", type=float)
    parser.add_argument("search_radius", help="search radius (decimal degrees)", type=float)
    parser.add_argument("g_limit", help="limiting Gaia G magnitude", type=float)
    parser.add_argument("--basename", help="file basename for output files", type=str, default="rgbsearch")
    parser.add_argument("--brightlimit",
                        help="stars brighter than this Gaia G limit are displayed with star symbols (default=8.0)",
                        type=float, default=8.0)
    parser.add_argument("--symbsize", help="multiplying factor for symbol size (default=1.0)",
                        type=float, default=1.0)
    parser.add_argument("--nonumbers", help="do not display star numbers in PDF chart", action="store_true")
    parser.add_argument("--noplot", help="skip PDF chart generation", action="store_true")
    parser.add_argument("--nocolor", help="do not use colors in PDF chart", action="store_true")
    parser.add_argument("--starhorse", help="include StarHorse av50, met50 and dist50 in rgbsearch_15m.csv",
                        action="store_true")
    parser.add_argument("--verbose", help="increase program verbosity", action="store_true")
    parser.add_argument("--debug", help="debug flag", action="store_true")

    args = parser.parse_args()

    if len(sys.argv) == 1:
        parser.print_usage()
        raise SystemExit()

    if args.ra_center < 0 or args.ra_center > 360:
        raise SystemExit('ERROR: right ascension out of valid range')
    if args.dec_center < -90 or args.dec_center > 90:
        raise SystemExit('ERROR: declination out of valid range')
    if args.search_radius < 0:
        raise SystemExit('ERROR: search radius must be > 0 degrees')
    if args.search_radius > MAX_SEARCH_RADIUS:
        raise SystemExit(f'ERROR: search radius must be <= {MAX_SEARCH_RADIUS} degrees')

    # check whether the auxiliary FITS binary table exists
    if args.starhorse:
        if args.debug:
            auxbintable = RGB_FROM_GAIA_ALLSKY
        else:
            auxbintable = EDR3_SOURCE_ID_PARAMS_15M_ALLSKY
    else:
        auxbintable = EDR3_SOURCE_ID_15M_ALLSKY
    if os.path.isfile(auxbintable):
        pass
    else:
        urldir = f'http://nartex.fis.ucm.es/~ncl/rgbphot/gaia/{auxbintable}'
        sys.stdout.write(f'Downloading {urldir}... (please wait)')
        sys.stdout.flush()
        urllib.request.urlretrieve(urldir, auxbintable)
        print(' ...OK!')

    # read the previous file
    try:
        with fits.open(auxbintable) as hdul_table:
            edr3_source_id_15M_allsky = hdul_table[1].data.source_id
            if args.starhorse:
                edr3_av50_15M_allsky = hdul_table[1].data.av50
                edr3_met50_15M_allsky = hdul_table[1].data.met50
                edr3_dist50_15M_allsky = hdul_table[1].data.dist50
                if args.debug:
                    edr3_b_rgb_15M_allsky = hdul_table[1].data.B_rgb
                    edr3_g_rgb_15M_allsky = hdul_table[1].data.G_rgb
                    edr3_r_rgb_15M_allsky = hdul_table[1].data.R_rgb
                    edr3_g_br_rgb_15M_allsky = hdul_table[1].data.G_BR_rgb
                    edr3_g_gaia_15M_allsky = hdul_table[1].data.G_gaia
                    edr3_bp_gaia_15M_allsky = hdul_table[1].data.BP_gaia
                    edr3_rp_gaia_15M_allsky = hdul_table[1].data.RP_gaia

    except FileNotFoundError:
        raise SystemExit(f'ERROR: unexpected problem while reading {EDR3_SOURCE_ID_15M_ALLSKY}')

    # define WCS
    naxis1 = 1024
    naxis2 = naxis1
    pixscale = 2 * args.search_radius / naxis1

    wcs_image = WCS(naxis=2)
    wcs_image.wcs.crpix = [naxis1 / 2, naxis2 / 2]
    wcs_image.wcs.crval = [args.ra_center, args.dec_center]
    wcs_image.wcs.cunit = ["deg", "deg"]
    wcs_image.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    wcs_image.wcs.cdelt = [-pixscale, pixscale]
    wcs_image.array_shape = [naxis1, naxis2]
    if args.verbose:
        print(wcs_image)

    # ---

    # EDR3 query
    query = f"""
    SELECT source_id, ra, dec,
    phot_g_mean_mag, phot_bp_mean_mag, phot_rp_mean_mag

    FROM gaiaedr3.gaia_source
    WHERE 1=CONTAINS(
      POINT('ICRS', {args.ra_center}, {args.dec_center}), 
      CIRCLE('ICRS',ra, dec, {args.search_radius}))
    AND phot_g_mean_mag IS NOT NULL 
    AND phot_bp_mean_mag IS NOT NULL 
    AND phot_rp_mean_mag IS NOT NULL
    AND phot_g_mean_mag < {args.g_limit}
    
    ORDER BY ra
    """
    sys.stdout.write('<STEP1> Starting cone search in Gaia EDR3... (please wait)\n  ')
    sys.stdout.flush()
    job = Gaia.launch_job_async(query)
    r_edr3 = job.get_results()
    # compute G_BP - G_RP colour
    r_edr3.add_column(
        Column(r_edr3['phot_bp_mean_mag'] - r_edr3['phot_rp_mean_mag'],
               name='bp_rp', unit=u.mag)
    )
    # colour cut in BP-RP
    mask_colour = np.logical_or((r_edr3['bp_rp'] <= -0.5), (r_edr3['bp_rp'] >= 2.0))
    r_edr3_colorcut = r_edr3[mask_colour]
    nstars = len(r_edr3)
    print(f'        --> {nstars} stars found')
    nstars_colorcut = len(r_edr3_colorcut)
    print(f'        --> {nstars_colorcut} stars outside -0.5 < G_BP-G_RP < 2.0')
    if nstars == 0:
        raise SystemExit('ERROR: no stars found. Change search parameters!')
    if args.verbose:
        r_edr3.pprint(max_width=1000)

    # ---

    # intersection with 15M star sample
    sys.stdout.write('<STEP2> Cross-matching EDR3 with 15M subsample... (please wait)')
    sys.stdout.flush()
    set1 = set(np.array(r_edr3['source_id']))
    set2 = set(edr3_source_id_15M_allsky)
    intersection = set2.intersection(set1)
    print(f'\n        --> {len(intersection)} stars in common with 15M sample')
    if args.verbose:
        print(len(set1), len(set2), len(intersection))

    # ---

    # DR2 query to identify variable stars
    query = f"""
    SELECT source_id, ra, dec, phot_g_mean_mag, phot_variable_flag

    FROM gaiadr2.gaia_source
    WHERE  1=CONTAINS(
      POINT('ICRS', {args.ra_center}, {args.dec_center}), 
      CIRCLE('ICRS',ra, dec, {args.search_radius}))
    AND phot_g_mean_mag < {args.g_limit}
    """
    sys.stdout.write('<STEP3> Looking for variable stars in Gaia DR2... (please wait)\n  ')
    sys.stdout.flush()
    job = Gaia.launch_job_async(query)
    r_dr2 = job.get_results()
    nstars_dr2 = len(r_dr2)
    if nstars_dr2 == 0:
        nvariables = 0
        mask_var = None
    else:
        if isinstance(r_dr2['phot_variable_flag'][0], bytes):
            mask_var = r_dr2['phot_variable_flag'] == b'VARIABLE'
        elif isinstance(r_dr2['phot_variable_flag'][0], str):
            mask_var = r_dr2['phot_variable_flag'] == 'VARIABLE'
        else:
            raise SystemExit('Unexpected type of data in column phot_variable_flag')
        nvariables = sum(mask_var)
        print(f'        --> {nstars_dr2} stars in DR2, ({nvariables} initial variables)')
    if nvariables > 0:
        if args.verbose:
            r_dr2[mask_var].pprint(max_width=1000)

    # ---

    # cross-match between DR2 and EDR3 to identify the variable stars
    dumstr = '('
    if nvariables > 0:
        # generate sequence of source_id of variable stars
        for i, item in enumerate(r_dr2[mask_var]['source_id']):
            if i > 0:
                dumstr += ', '
            dumstr += f'{item}'
        dumstr += ')'
        # cross-match
        query = f"""
        SELECT *
        FROM gaiaedr3.dr2_neighbourhood
        WHERE dr2_source_id IN {dumstr}
        ORDER BY angular_distance
        """
        sys.stdout.write('<STEP4> Cross-matching variables in DR2 with stars in EDR3... (please wait)\n  ')
        sys.stdout.flush()
        job = Gaia.launch_job_async(query)
        r_cross_var = job.get_results()
        if args.verbose:
            r_cross_var.pprint(max_width=1000)
        nvariables = len(r_cross_var)
        if nvariables > 0:
            # check that the variables pass the same selection as the EDR3 stars
            # (this includes de colour cut)
            mask_var = []
            for item in r_cross_var['dr3_source_id']:
                if item in r_edr3['source_id']:
                    mask_var.append(True)
                else:
                    mask_var.append(False)
            r_cross_var = r_cross_var[mask_var]
            nvariables = len(r_cross_var)
            if args.verbose:
                r_cross_var.pprint(max_width=1000)
        else:
            r_cross_var = None
    else:
        r_cross_var = None  # Avoid PyCharm warning
    print(f'        --> {nvariables} variable(s) in selected EDR3 star sample')

    # ---

    sys.stdout.write('<STEP5> Computing RGB magnitudes...')
    sys.stdout.flush()
    # predict RGB magnitudes
    coef_B = np.array([-0.13748689, 0.44265552, 0.37878846, -0.14923841, 0.09172474, -0.02594726])
    coef_G = np.array([-0.02330159, 0.12884074, 0.22149167, -0.1455048, 0.10635149, -0.0236399])
    coef_R = np.array([0.10979647, -0.14579334, 0.10747392, -0.1063592, 0.08494556, -0.01368962])
    coef_X = np.array([-0.01252185, 0.13983574, 0.23688188, -0.10175532, 0.07401939, -0.0182115])

    poly_B = Polynomial(coef_B)
    poly_G = Polynomial(coef_G)
    poly_R = Polynomial(coef_R)
    poly_X = Polynomial(coef_X)

    r_edr3.add_column(
        Column(np.round(r_edr3['phot_g_mean_mag'] + poly_B(r_edr3['bp_rp']), 2),
               name='b_rgb', unit=u.mag, format='.2f'), index=3
    )
    r_edr3.add_column(
        Column(np.round(r_edr3['phot_g_mean_mag'] + poly_G(r_edr3['bp_rp']), 2),
               name='g_rgb', unit=u.mag, format='.2f'), index=4
    )
    r_edr3.add_column(
        Column(np.round(r_edr3['phot_g_mean_mag'] + poly_R(r_edr3['bp_rp']), 2),
               name='r_rgb', unit=u.mag, format='.2f'), index=5
    )
    r_edr3.add_column(
        Column(np.round(r_edr3['phot_g_mean_mag'] + poly_X(r_edr3['bp_rp']), 2),
               name='g_br_rgb', unit=u.mag, format='.2f'), index=6
    )
    print('OK')
    if args.verbose:
        r_edr3.pprint(max_width=1000)

    # ---

    sys.stdout.write('<STEP6> Saving output CSV files...')
    sys.stdout.flush()
    outtypes = ['edr3', '15m', 'var']
    outtypes_color = {'edr3': 'black', '15m': 'red', 'var': 'blue'}
    r_edr3.add_column(Column(np.zeros(len(r_edr3)), name='number_csv', dtype=int))
    for item in outtypes:
        r_edr3.add_column(Column(np.zeros(len(r_edr3)), name=f'number_{item}', dtype=int))
    outlist = [f'./{args.basename}_{ftype}.csv' for ftype in outtypes]
    filelist = glob.glob('./*.csv')
    # remove previous versions of the output files (if present)
    for file in outlist:
        if file in filelist:
            try:
                os.remove(file)
            except:
                print(f'ERROR: while deleting existing file {file}')
    # columns to be saved (use a list to guarantee the same order)
    outcolumns_list = ['source_id', 'ra', 'dec', 'b_rgb', 'g_rgb', 'r_rgb', 'g_br_rgb',
                       'phot_g_mean_mag', 'phot_bp_mean_mag', 'phot_rp_mean_mag']
    # define column format with a dictionary
    outcolumns = {'source_id': '19d',
                  'ra': '14.9f',
                  'dec': '14.9f',
                  'b_rgb': '6.2f',
                  'g_rgb': '6.2f',
                  'r_rgb': '6.2f',
                  'g_br_rgb': '6.2f',
                  'phot_g_mean_mag': '8.4f',
                  'phot_bp_mean_mag': '8.4f',
                  'phot_rp_mean_mag': '8.4f'
                  }
    if set(outcolumns_list) != set(outcolumns.keys()):
        raise SystemExit('ERROR: check outcolumns_list and outcolumns')
    csv_header = 'number,' + ','.join(outcolumns_list)
    flist = []
    for ftype in outtypes:
        f = open(f'{args.basename}_{ftype}.csv', 'wt')
        flist.append(f)
        if args.starhorse and ftype == '15m':
            if args.debug:
                f.write(csv_header + ',av50,met50,dist50,b_rgb2,g_rgb2,r_rgb2,g_br_rgb2,' +
                        'phot_g_mean_mag2,phot_bp_mean_mag2,phot_rp_mean_mag2\n')
            else:
                f.write(csv_header + ',av50,met50,dist50\n')
        else:
            f.write(csv_header + '\n')
    # save each star in its corresponding output file
    krow = np.ones(len(outtypes), dtype=int)
    for irow, row in enumerate(r_edr3):
        cout = []
        for item in outcolumns_list:
            cout.append(eval("f'{row[item]:" + f'{outcolumns[item]}' + "}'"))
        iout = 0
        if nvariables > 0:
            if row['source_id'] in r_cross_var['dr3_source_id']:
                iout = 2
        if iout == 0:
            if row['source_id'] in intersection:
                iout = 1
                if args.starhorse:
                    iloc = np.argwhere(edr3_source_id_15M_allsky == row['source_id'])[0][0]
                    cout.append(f"{edr3_av50_15M_allsky[iloc]:7.3f}")
                    cout.append(f"{edr3_met50_15M_allsky[iloc]:7.3f}")
                    cout.append(f"{edr3_dist50_15M_allsky[iloc]:7.3f}")
                    if args.debug:
                        cout.append(f"{edr3_b_rgb_15M_allsky[iloc]:6.2f}")
                        cout.append(f"{edr3_g_rgb_15M_allsky[iloc]:6.2f}")
                        cout.append(f"{edr3_r_rgb_15M_allsky[iloc]:6.2f}")
                        cout.append(f"{edr3_g_br_rgb_15M_allsky[iloc]:6.2f}")
                        cout.append(f"{edr3_g_gaia_15M_allsky[iloc]:8.4f}")
                        cout.append(f"{edr3_bp_gaia_15M_allsky[iloc]:8.4f}")
                        cout.append(f"{edr3_rp_gaia_15M_allsky[iloc]:8.4f}")
        flist[iout].write(f'{krow[iout]:6d}, ' + ','.join(cout) + '\n')
        r_edr3[irow]['number_csv'] = iout
        r_edr3[irow][f'number_{outtypes[iout]}'] = krow[iout]
        krow[iout] += 1
    for f in flist:
        f.close()
    print('OK')

    if args.verbose:
        print(r_edr3)

    if args.noplot:
        raise SystemExit()

    # ---

    sys.stdout.write('<STEP7> Generating PDF plot...')
    sys.stdout.flush()
    # generate plot
    r_edr3.sort('phot_g_mean_mag')
    if args.verbose:
        print('')
        r_edr3.pprint(max_width=1000)

    symbol_size = args.symbsize * (50 / np.array(r_edr3['phot_g_mean_mag'])) ** 2.5
    ra_array = np.array(r_edr3['ra'])
    dec_array = np.array(r_edr3['dec'])

    c = SkyCoord(ra=ra_array * u.degree, dec=dec_array * u.degree, frame='icrs')
    x_pix, y_pix = wcs_image.world_to_pixel(c)

    fig = plt.figure(figsize=(11, 10))
    ax = plt.subplot(projection=wcs_image)
    iok = r_edr3['phot_g_mean_mag'] < args.brightlimit
    if args.nocolor:
        sc = ax.scatter(x_pix[iok], y_pix[iok], marker='*', color='grey',
                        edgecolors='black', linewidth=0.2, s=symbol_size[iok])
        ax.scatter(x_pix[~iok], y_pix[~iok], marker='.', color='grey',
                   edgecolors='black', linewidth=0.2, s=symbol_size[~iok])
    else:
        cmap = plt.cm.get_cmap('jet')
        sc = ax.scatter(x_pix[iok], y_pix[iok], marker='*',
                        edgecolors='black', linewidth=0.2, s=symbol_size[iok],
                        cmap=cmap, c=r_edr3[iok]['bp_rp'], vmin=-0.5, vmax=2.0)
        ax.scatter(x_pix[~iok], y_pix[~iok], marker='.',
                   edgecolors='black', linewidth=0.2, s=symbol_size[~iok],
                   cmap=cmap, c=r_edr3[~iok]['bp_rp'], vmin=-0.5, vmax=2.0)

    # display numbers if requested
    if not args.nonumbers:
        for irow in range(len(r_edr3)):
            number_csv = r_edr3[irow]['number_csv']
            text = r_edr3[irow][f'number_{outtypes[number_csv]}']
            ax.text(x_pix[irow], y_pix[irow], text,
                    color=outtypes_color[outtypes[number_csv]], fontsize='5',
                    horizontalalignment='left', verticalalignment='bottom')

    # stars outside the -0.5 < G_BP - G_RP < 2.0 colour cut
    if nstars_colorcut > 0:
        mask_colour = np.logical_or((r_edr3['bp_rp'] <= -0.5), (r_edr3['bp_rp'] >= 2.0))
        iok = np.argwhere(mask_colour)
        ax.scatter(x_pix[iok], y_pix[iok], s=240, marker='D', facecolors='none', edgecolors='grey', linewidth=0.5)

    # variable stars
    if nvariables > 0:
        sorter = np.argsort(r_edr3['source_id'])
        iok = np.array(sorter[np.searchsorted(r_edr3['source_id'], r_cross_var['dr3_source_id'], sorter=sorter)])
        ax.scatter(x_pix[iok], y_pix[iok], s=240, marker='s', facecolors='none', edgecolors='blue', linewidth=0.5)

    # stars in 15M sample
    if len(intersection) > 0:
        sorter = np.argsort(r_edr3['source_id'])
        iok = np.array(sorter[np.searchsorted(r_edr3['source_id'], np.array(list(intersection)), sorter=sorter)])
        ax.scatter(x_pix[iok], y_pix[iok], s=240, marker='o', facecolors='none',
                   edgecolors=outtypes_color['15m'], linewidth=0.5)

    ax.scatter(0.03, 0.96, s=240, marker='o', facecolors='white',
               edgecolors=outtypes_color['15m'], linewidth=0.5,
               transform=ax.transAxes)
    ax.text(0.06, 0.96, 'star in 15M sample', fontsize=12, backgroundcolor='white',
            horizontalalignment='left', verticalalignment='center', transform=ax.transAxes)

    ax.scatter(0.03, 0.92, s=240, marker='s', facecolors='white',
               edgecolors=outtypes_color['var'], linewidth=0.5,
               transform=ax.transAxes)
    ax.text(0.06, 0.92, 'variable in Gaia DR2', fontsize=12, backgroundcolor='white',
            horizontalalignment='left', verticalalignment='center', transform=ax.transAxes)

    ax.scatter(0.03, 0.88, s=240, marker='D', facecolors='white', edgecolors='grey', linewidth=0.5,
               transform=ax.transAxes)
    ax.text(0.06, 0.88, 'outside colour range', fontsize=12, backgroundcolor='white',
            horizontalalignment='left', verticalalignment='center', transform=ax.transAxes)

    ax.set_xlabel('ra')
    ax.set_ylabel('dec')

    ax.set_aspect('equal')

    if not args.nocolor:
        cbaxes = fig.add_axes([0.683, 0.81, 0.15, 0.02])
        cbar = plt.colorbar(sc, cax=cbaxes, orientation='horizontal', format='%1.0f')
        cbar.ax.tick_params(labelsize=12)
        cbar.set_label(label=r'$G_{\rm BP}-G_{\rm RP}$', size=12, backgroundcolor='white')

    ax.text(0.98, 0.96, f'Field radius: {args.search_radius:.4f} degree', fontsize=12, backgroundcolor='white',
            horizontalalignment='right', verticalalignment='center', transform=ax.transAxes)
    ax.text(0.02, 0.06, r'$\alpha_{\rm center}$:', fontsize=12, backgroundcolor='white',
            horizontalalignment='left', verticalalignment='bottom', transform=ax.transAxes)
    ax.text(0.30, 0.06, f'{args.ra_center:.4f} degree', fontsize=12, backgroundcolor='white',
            horizontalalignment='right', verticalalignment='bottom', transform=ax.transAxes)
    ax.text(0.02, 0.02, r'$\delta_{\rm center}$:', fontsize=12, backgroundcolor='white',
            horizontalalignment='left', verticalalignment='bottom', transform=ax.transAxes)
    ax.text(0.30, 0.02, f'{args.dec_center:+.4f} degree', fontsize=12, backgroundcolor='white',
            horizontalalignment='right', verticalalignment='bottom', transform=ax.transAxes)
    ax.text(0.98, 0.02, f'RGBfromGaiaEDR3, version {VERSION}', fontsize=12, backgroundcolor='white',
            horizontalalignment='right', verticalalignment='bottom', transform=ax.transAxes)

    ax.set_axisbelow(True)
    overlay = ax.get_coords_overlay('icrs')
    overlay.grid(color='black', ls='dotted')

    plt.savefig(f'{args.basename}.pdf')
    plt.close(fig)
    if args.verbose:
        pass
    else:
        print('OK')


if __name__ == "__main__":

    main()
