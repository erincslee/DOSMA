import os
import numpy as np
import argparse
import models
import SimpleITK as sitk

import utils
import dess_utils
import im_utils


def generate_mask(dicom_path, save_path, tissue_strs, dicom_ext, echos):
    """Generate mask for dicoms and write as 3D tiff
    :param dicom_path: string path to directory where dicoms are stored
    :param save_path: string path to directory where masks should be stored
    :param tissue_strs: list of tissues to segment
    :param dicom_ext: string extension for dicom files. Default is None, meaning the extension will not be checked
    :param echos: Number of echos the dicoms represent (OAI = 1, DESS = 2)
    """
    volume, _ = utils.load_dicom(dicom_path, dicom_ext)

    subvolumes = utils.split_volume(volume, echos)

    # Use first echo for segmentation
    volume = subvolumes[0]
    volume = utils.whiten_volume(volume)

    masks = dict()

    print('')
    for tissue in tissue_strs:
        print('Segmenting %s...' % tissue)
        mask = models.generate_mask(volume, tissue)
        assert(volume.shape == mask.shape)

        # Output mask as 3d tiff
        mask_filepath = os.path.join(save_path, tissue + '.tiff')
        im_utils.write_3d(mask_filepath, mask)

        masks[tissue] = mask

    return masks


def calculate_t2_maps(dicom_path, save_path, dicom_ext, masks):
    print('')
    print('Calculating T2 map...')
    volume, ref_dicom = utils.load_dicom(dicom_path, dicom_ext)

    t2_map = dess_utils.calc_dess_t2_map(volume, ref_dicom)

    t2_vals = dict()
    for tissue in masks.keys():
        mask = masks[tissue]
        t2_vals[tissue] = dess_utils.get_tissue_t2(t2_map, mask, tissue)

    return t2_vals


def parse_args():
    """Parse arguments given through command line (argv)

    :raises ValueError if dicom path is not provided
    :raise NotADirectoryError if dicom path does not exist or is not a directory
    """
    parser = argparse.ArgumentParser(description='Segment MRI knee volumes using ARCHITECTURE (ADD SOURCE)',
                                     epilog='NOTE: by default all tissues will be segmented unless specific flags are provided')

    # Dicom and results paths
    parser.add_argument('-d', '--dicom', metavar='D', type=str, nargs=1,
                        help='path to directory storing dicom files')
    parser.add_argument('-s', '--save', metavar='S', type=str, default='', nargs='?',
                        help='path to directory to save mask. Default: D')

    # If user wants to filter by extension, allow them to specify extension
    parser.add_argument('-e', '--ext', metavar='E', type=str, default=None, nargs='?',
                        help='extension of dicom files')

    # Add arguments for each tissue
    # If user specifies any of these flags, only segment that tissue
    # Else by default, segment all tissues
    parser.add_argument('-f', action='store_const', const=models.FEMORAL_CARTILAGE_STR, default=None,
                        help='segment femoral cartilage')
    parser.add_argument('-t', action='store_const', const=models.TIBIAL_CARTILAGE_STR, default=None,
                        help='segment tibial cartilage')
    parser.add_argument('-m', action='store_const', const=models.MENISCUS_STR, default=None,
                        help='segment meniscus')
    parser.add_argument('-p', action='store_const', const=models.PATELLAR_CARTILAGE_STR, default=None,
                        help='segment patellar cartilage')

    # Dess arguments
    parser.add_argument('--dess', action='store_const', const=True, default=False,
                        help='are dicoms acquired using DESS sequence')
    parser.add_argument('--t2', action='store_const', const=True, default=False,
                        help="calculate t2 map for tissues. Only compatible with DESS")

    # Neural network arguments
    parser.add_argument('--batch_size', metavar='B', type=int, default=32, nargs='?',
                        help='batch size for inference. Default: 32')
    parser.add_argument('--gpu', metavar='G', type=str, default=None, nargs='?', help='gpu id to use')

    args = parser.parse_args()
    gpu = args.gpu

    if gpu is not None:
        os.environ['CUDA_VISIBLE_DEVICES'] = gpu

    try:
        dicom_path = args.dicom[0]
    except Exception:
        raise ValueError("No path to dicom provided")

    save_path = args.save
    if save_path == '':
        save_path = dicom_path

    try:
        if not os.path.isdir(dicom_path):
            raise ValueError
    except ValueError:
        raise NotADirectoryError("Directory \'%s\' does not exist" % dicom_path)

    if not os.path.isdir(save_path):
        os.makedirs(save_path)

    # Dicom extension
    dicom_ext = args.ext

    dess = args.dess
    calculate_t2_maps = args.t2

    if (not dess and calculate_t2_maps):
        raise ValueError('calculating t2 maps only compatible with DESS dicoms. Please specify the --dess flag')

    # number of echos in volume
    num_echos = dess_utils.NUM_ECHOS if dess else 1

    # Get batch size
    models.BATCH_SIZE = args.batch_size

    # Parse tissues to segment
    # If user doesn't specify any flags, segment all tissues
    tissue_strs = [args.f, args.t, args.m, args.p]
    tissue_strs = [x for x in tissue_strs if x is not None]
    if len(tissue_strs) == 0:
        tissue_strs = [models.FEMORAL_CARTILAGE_STR, models.TIBIAL_CARTILAGE_STR, models.MENISCUS_STR, models.PATELLAR_CARTILAGE_STR]

    masks = generate_mask(dicom_path, save_path, tissue_strs, dicom_ext, num_echos)

    # Calculate t2 maps
    if dess and calculate_t2_maps:
        calculate_t2_maps(dicom_path, save_path, dicom_ext, masks)


if __name__ == '__main__':
    parse_args()
