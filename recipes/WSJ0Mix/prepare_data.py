"""
The .csv preperation functions for WSJ0-Mix.

Author
 * Cem Subakan 2020

 """

import os
import numpy as np
from speechbrain.dataio.dataio import write_audio
import csv


def prepare_wsjmix(
    datapath,
    savepath,
    n_spks=2,
    skip_prep=False,
    librimix_addnoise=False,
    fs=8000,
):
    """
    Prepared wsj2mix if n_spks=2 and wsj3mix if n_spks=3.

    Arguments:
    ----------
        datapath (str) : path for the wsj0-mix dataset.
        savepath (str) : path where we save the csv file.
        n_spks (int): number of speakers
        skip_prep (bool): If True, skip data preparation
        librimix_addnoise: If True, add whamnoise to librimix datasets
    """

    if skip_prep:
        return

    if "wsj" in datapath:

        if n_spks == 2:
            create_wsj_csv(datapath, savepath)
        elif n_spks == 3:
            create_wsj_csv_3spks(datapath, savepath)
        else:
            raise ValueError("Unsupported Number of Speakers")
    else:
        print("Creating a csv file for a custom dataset")
        create_custom_dataset(datapath, savepath)


def create_custom_dataset(
    datapath,
    savepath,
    dataset_name="custom",
    set_types=["train", "valid", "test"],
    folder_names={
        "source1": "source1",
        "source2": "source2",
        "mixture": "mixture",
    },
):
    """
    This function creates the csv file for a custom source separation dataset
    """

    for set_type in set_types:
        mix_path = os.path.join(datapath, set_type, folder_names["mixture"])
        s1_path = os.path.join(datapath, set_type, folder_names["source1"])
        s2_path = os.path.join(datapath, set_type, folder_names["source2"])

        files = os.listdir(mix_path)

        mix_fl_paths = [os.path.join(mix_path, fl) for fl in files]
        s1_fl_paths = [os.path.join(s1_path, fl) for fl in files]
        s2_fl_paths = [os.path.join(s2_path, fl) for fl in files]

        csv_columns = [
            "ID",
            "duration",
            "mix_wav",
            "mix_wav_format",
            "mix_wav_opts",
            "s1_wav",
            "s1_wav_format",
            "s1_wav_opts",
            "s2_wav",
            "s2_wav_format",
            "s2_wav_opts",
            "noise_wav",
            "noise_wav_format",
            "noise_wav_opts",
        ]

        with open(
            os.path.join(savepath, dataset_name + "_" + set_type + ".csv"), "w"
        ) as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=csv_columns)
            writer.writeheader()
            for i, (mix_path, s1_path, s2_path) in enumerate(
                zip(mix_fl_paths, s1_fl_paths, s2_fl_paths)
            ):

                row = {
                    "ID": i,
                    "duration": 1.0,
                    "mix_wav": mix_path,
                    "mix_wav_format": "wav",
                    "mix_wav_opts": None,
                    "s1_wav": s1_path,
                    "s1_wav_format": "wav",
                    "s1_wav_opts": None,
                    "s2_wav": s2_path,
                    "s2_wav_format": "wav",
                    "s2_wav_opts": None,
                }
                writer.writerow(row)


def create_wsj_csv(datapath, savepath):
    """
    This function creates the csv files to get the speechbrain data loaders for the wsj0-2mix dataset.

    Arguments:
        datapath (str) : path for the wsj0-mix dataset.
        savepath (str) : path where we save the csv file
    """
    for set_type in ["tr", "cv", "tt"]:
        mix_path = os.path.join(datapath, "wav8k/min/" + set_type + "/mix/")
        s1_path = os.path.join(datapath, "wav8k/min/" + set_type + "/s1/")
        s2_path = os.path.join(datapath, "wav8k/min/" + set_type + "/s2/")

        files = os.listdir(mix_path)

        mix_fl_paths = [mix_path + fl for fl in files]
        s1_fl_paths = [s1_path + fl for fl in files]
        s2_fl_paths = [s2_path + fl for fl in files]

        csv_columns = [
            "ID",
            "duration",
            "mix_wav",
            "mix_wav_format",
            "mix_wav_opts",
            "s1_wav",
            "s1_wav_format",
            "s1_wav_opts",
            "s2_wav",
            "s2_wav_format",
            "s2_wav_opts",
        ]

        with open(savepath + "/wsj_" + set_type + ".csv", "w") as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=csv_columns)
            writer.writeheader()
            for i, (mix_path, s1_path, s2_path) in enumerate(
                zip(mix_fl_paths, s1_fl_paths, s2_fl_paths)
            ):

                row = {
                    "ID": i,
                    "duration": 1.0,
                    "mix_wav": mix_path,
                    "mix_wav_format": "wav",
                    "mix_wav_opts": None,
                    "s1_wav": s1_path,
                    "s1_wav_format": "wav",
                    "s1_wav_opts": None,
                    "s2_wav": s2_path,
                    "s2_wav_format": "wav",
                    "s2_wav_opts": None,
                }
                writer.writerow(row)


def create_wsj_csv_3spks(datapath, savepath):
    """
    This function creates the csv files to get the speechbrain data loaders for the wsj0-3mix dataset.

    Arguments:
        datapath (str) : path for the wsj0-mix dataset.
        savepath (str) : path where we save the csv file
    """
    for set_type in ["tr", "cv", "tt"]:
        mix_path = os.path.join(datapath, "wav8k/min/" + set_type + "/mix/")
        s1_path = os.path.join(datapath, "wav8k/min/" + set_type + "/s1/")
        s2_path = os.path.join(datapath, "wav8k/min/" + set_type + "/s2/")
        s3_path = os.path.join(datapath, "wav8k/min/" + set_type + "/s3/")

        files = os.listdir(mix_path)

        mix_fl_paths = [mix_path + fl for fl in files]
        s1_fl_paths = [s1_path + fl for fl in files]
        s2_fl_paths = [s2_path + fl for fl in files]
        s3_fl_paths = [s3_path + fl for fl in files]

        csv_columns = [
            "ID",
            "duration",
            "mix_wav",
            "mix_wav_format",
            "mix_wav_opts",
            "s1_wav",
            "s1_wav_format",
            "s1_wav_opts",
            "s2_wav",
            "s2_wav_format",
            "s2_wav_opts",
            "s3_wav",
            "s3_wav_format",
            "s3_wav_opts",
        ]

        with open(savepath + "/wsj_" + set_type + ".csv", "w") as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=csv_columns)
            writer.writeheader()
            for i, (mix_path, s1_path, s2_path, s3_path) in enumerate(
                zip(mix_fl_paths, s1_fl_paths, s2_fl_paths, s3_fl_paths)
            ):

                row = {
                    "ID": i,
                    "duration": 1.0,
                    "mix_wav": mix_path,
                    "mix_wav_format": "wav",
                    "mix_wav_opts": None,
                    "s1_wav": s1_path,
                    "s1_wav_format": "wav",
                    "s1_wav_opts": None,
                    "s2_wav": s2_path,
                    "s2_wav_format": "wav",
                    "s2_wav_opts": None,
                    "s3_wav": s3_path,
                    "s3_wav_format": "wav",
                    "s3_wav_opts": None,
                }
                writer.writerow(row)


def save_mixture(
    s1,
    s2,
    min_max,
    weight_1,
    weight_2,
    num_files,
    lev1,
    lev2,
    save_fs,
    output_dir,
    data_type,
    mix_name,
    i,
):
    """
    This function creates the mixtures, and saves them

    Arguments:
        s1, s1 (numpy array): source1 and source2 wav files in numpy array.
        weight_1, weight_2 (float): weights for source1 and source2 respectively.
        num_files (int): number of files
        lev1, lev2 (float): levels for each souce obtained with octave.activlev() function
        save_fs (str): in ['wav8k', 'wav16k']
        output_dir (str): the save directory
        data_type (str): in ['tr', 'cv', 'tt']
        mix_name (str): name given to the mixture. (see the main function get_wsj_files())
        i (int): number of the mixture. (see the main function get_wsj_files())

    """
    scaling = np.zeros((num_files, 2))
    scaling16bit = np.zeros((num_files, 1))

    if min_max == "max":
        mix_len = max(s1.shape[0], s2.shape[0])

        s1 = np.pad(
            s1, (0, mix_len - s1.shape[0]), "constant", constant_values=(0, 0),
        )
        s2 = np.pad(
            s2, (0, mix_len - s2.shape[0]), "constant", constant_values=(0, 0),
        )
    else:
        mix_len = min(s1.shape[0], s2.shape[0])

        s1 = s1[:mix_len]
        s2 = s2[:mix_len]

    mix = s1 + s2

    max_amp = max(np.abs(mix).max(), np.abs(s1).max(), np.abs(s2).max(),)
    mix_scaling = 1 / max_amp * 0.9
    s1 = mix_scaling * s1
    s2 = mix_scaling * s2
    mix = mix_scaling * mix

    scaling[i, 0] = weight_1 * mix_scaling / np.sqrt(lev1)
    scaling[i, 1] = weight_2 * mix_scaling / np.sqrt(lev2)
    scaling16bit[i] = mix_scaling

    sampling_rate = 8000 if save_fs == "wav8k" else 16000

    write_audio(
        s1,
        output_dir
        + "/"
        + save_fs
        + "/"
        + min_max
        + "/"
        + data_type
        + "/s1/"
        + mix_name
        + ".wav",
        sampling_rate=sampling_rate,
    )
    write_audio(
        s2,
        output_dir
        + "/"
        + save_fs
        + "/"
        + min_max
        + "/"
        + data_type
        + "/s2/"
        + mix_name
        + ".wav",
        sampling_rate=sampling_rate,
    )
    write_audio(
        mix,
        output_dir
        + "/"
        + save_fs
        + "/"
        + min_max
        + "/"
        + data_type
        + "/mix/"
        + mix_name
        + ".wav",
        sampling_rate=sampling_rate,
    )
    return scaling, scaling16bit
