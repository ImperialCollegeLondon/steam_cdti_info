"""
Script to convert cardiac DTI DICOMs to NIfTI plus extra side files
Including csv file with the nominal intervals and acquisition times for each image.
"""

import sys
import glob
import os
import pydicom
import pandas as pd


def get_nominal_interval(
    c_dicom_header: dict, dicom_type: int, frame_idx: int
) -> float:
    """
    Get the nominal interval from the DICOM header

    Parameters
    ----------
    c_dicom_header
    dicom_type
    frame_idx

    Returns
    -------
    Nominal interval

    """
    if dicom_type == 2:
        val = float(
            c_dicom_header["PerFrameFunctionalGroupsSequence"][frame_idx][
                "CardiacSynchronizationSequence"
            ][0]["RRIntervalTimeNominal"]
        )
        return val

    elif dicom_type == 1:
        val = float(c_dicom_header["NominalInterval"])
        return val


def get_acquisition_time(c_dicom_header: dict, dicom_type: int, frame_idx: int) -> str:
    """
    Get acquisition time string

    Parameters
    ----------
    c_dicom_header
    dicom_type
    frame_idx

    Returns
    -------
    Acquisition time

    """
    if dicom_type == 2:
        return c_dicom_header["PerFrameFunctionalGroupsSequence"][frame_idx][
            "FrameContentSequence"
        ][0]["FrameAcquisitionDateTime"][8:]

    elif dicom_type == 1:
        return c_dicom_header["AcquisitionTime"]


def get_acquisition_date(c_dicom_header: dict, dicom_type: int, frame_idx: int) -> str:
    """
    Get acquisition date string.

    Parameters
    ----------
    c_dicom_header
    dicom_type
    frame_idx

    Returns
    -------
    Acquisition date

    """
    if dicom_type == 2:
        return c_dicom_header["PerFrameFunctionalGroupsSequence"][frame_idx][
            "FrameContentSequence"
        ][0]["FrameAcquisitionDateTime"][:8]

    elif dicom_type == 1:
        return c_dicom_header["AcquisitionDate"]


def get_nii_file_suffix(c_dicom_header: dict, dicom_type: int, frame_idx: int) -> str:
    """
    Build the suffix nii file name corresponding to the current DICOM image

    Parameters
    ----------
    c_dicom_header
    dicom_type
    frame_idx

    Returns
    -------
    Suffix string

    """
    if dicom_type == 2:
        suffix = (
            c_dicom_header["SeriesDescription"]
            + "_"
            + c_dicom_header["SeriesDate"]
            + str(round((float(c_dicom_header["StudyTime"]))))
            + "_"
            + str(c_dicom_header["SeriesNumber"])
        )
        suffix = suffix.replace(" ", "_")
        return suffix

    elif dicom_type == 1:
        suffix = (
            c_dicom_header["SeriesDescription"]
            + "_"
            + c_dicom_header["SeriesDate"]
            + str(round((float(c_dicom_header["StudyTime"]))))
            + "_"
            + str(c_dicom_header["SeriesNumber"])
        )
        suffix = suffix.replace(" ", "_")
        return suffix


def dictify(ds: pydicom.dataset.Dataset) -> dict:
    """
    Turn a pydicom Dataset into a dict with keys derived from the Element tags.
    Private info is not collected, because we cannot access it with the keyword.
    So we need to manually fish the diffusion information in the old DICOMs.

    Parameters
    ----------
    ds : pydicom.dataset.Dataset
        The Dataset to dictify

    Returns
    -------
    DICOM header as a dict
    """

    output = dict()
    # iterate over all non private fields
    for elem in ds:
        if elem.VR != "SQ":
            output[elem.keyword] = elem.value
        else:
            output[elem.keyword] = [dictify(item) for item in elem]

    # add manually private diffusion fields if they exist
    if [0x0019, 0x100C] in ds:
        output["DiffusionBValue"] = ds[0x0019, 0x100C].value
    if [0x0019, 0x100E] in ds:
        output["DiffusionGradientDirection"] = ds[0x0019, 0x100E].value
    return output


def get_data_from_dicoms_and_export(dicom_path: str, output_path: str):

    # create output folder if it does not exist
    if not os.path.exists(output_path):
        os.makedirs(output_path)

    # run the dcm2niix command
    run_command = "dcm2niix -v 0 -o " + output_path + " " + dicom_path
    os.system(run_command)
    print("=============================================")
    print("dcm2niix command executed successfully!")
    print("=============================================")

    # list all the DICOM files
    dicom_files = glob.glob(os.path.join(dicom_path, "*.dcm"))
    dicom_files.sort()

    # collect some header info from the first DICOM
    ds = pydicom.dcmread(open(dicom_files[0], "rb"))

    # check DICOM header version: 1-legacy_header, 2-modern-header
    # also check the number of images inside each DICOM image
    dicom_type = 0
    if "PerFrameFunctionalGroupsSequence" in ds:
        dicom_type = 2
        # How many images in one DICOM file?
        n_images_per_file = len(ds.PerFrameFunctionalGroupsSequence)
    else:
        dicom_type = 1
        n_images_per_file = 1

    # create a list with the DICOM header fields
    df = []
    # loop over each DICOM file
    for idx, file_name in enumerate(dicom_files):
        # read current DICOM
        ds = pydicom.dcmread(open(file_name, "rb"))

        # convert header into a dict
        c_dicom_header = dictify(ds)

        # loop over each image in the current DICOM file
        for frame_idx in range(n_images_per_file):

            # append values (will be a row in the dataframe)
            df.append(
                (
                    # file name
                    os.path.basename(file_name),
                    # nominal interval
                    get_nominal_interval(c_dicom_header, dicom_type, frame_idx),
                    # acquisition time
                    get_acquisition_time(c_dicom_header, dicom_type, frame_idx),
                    # acquisition date
                    get_acquisition_date(c_dicom_header, dicom_type, frame_idx),
                    # nii file name suffix
                    get_nii_file_suffix(c_dicom_header, dicom_type, frame_idx),
                )
            )

    # column labels for the dataframe and for the csv file
    column_labels = [
        "file_name",
        "nominal_interval_(msec)",
        "acquisition_time",
        "acquisition_date",
        "nii_file_suffix",
    ]

    # create a dataframe from the list
    df = pd.DataFrame(
        df,
        columns=column_labels,
    )

    # sort dataframe by acquisition time
    df = df.sort_values(by=["acquisition_date", "acquisition_time"])

    # save dataframe as a csv file in the output folder
    df.to_csv(
        os.path.join(output_path, "rr_timings.csv"),
        columns=column_labels,
        index=False,
    )

    print("=============================================")
    print("csv file exported successfully!")
    print("=============================================")


if __name__ == "__main__":
    # arguments from command line
    # path to where to store nii and other files
    output_path = sys.argv[1]
    # path to the DICOMs folder
    dicom_path = sys.argv[2]
    # run main function
    get_data_from_dicoms_and_export(dicom_path, output_path)
