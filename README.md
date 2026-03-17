# Disagreement Detection Dataset (CHI '26)

This repository contains the multimodal dataset accompanying our CHI 2026 work on disagreement detection. The dataset is organized around participant responses to image-caption judgment trials built on top of MS COCO images and includes gaze traces, facial behavior signals, aggregate feature tables, AOI definitions, and visualization assets.

## Overview

The repository currently contains:

- 4,092 participant-stimulus trials in the per-sample facial and gaze exports.
- 154 unique MS COCO stimuli, identified by the `stimuli` column in the aggregate CSV files and by zero-padded image IDs in `AOI_Data`.
- 30 unique `user_id` values in the aggregate feature tables.
- Two boolean annotations exposed as `label` and `ground_truth_rating` in the aggregate exports.

At a high level, each dataset entry links a user response to an image-caption stimulus, along with gaze and facial measurements recorded during that trial. The per-sample CSV and PNG files use filenames of the form:

```text
<user_id>_<stimuli>_<label>_<ground_truth_rating>.<ext>
```

Example:

```text
A01_102281_False_False.csv
```

In the aggregate tables, the same entry is represented through the columns `user_id`, `stimuli`, `label`, and `ground_truth_rating`.

## Task Framing

The paper studies disagreement detection from multimodal human behavior. In this release, the experimental unit is an image-caption trial tied to an MS COCO image ID, and the provided modalities capture how a participant visually inspected and reacted to that trial.

The dataset structure makes the task explicit:

- `AOI_Data` contains an `image` AOI plus word-level AOIs for the caption shown with the image.
- Each stimulus has two AOI layouts, stored under `AOI_Data/A` and `AOI_Data/B`, corresponding to two caption variants for the same image.
- Across the 154 stimuli, 81 A/B pairs differ textually, often through a minimal content-word substitution such as `train` versus `car`, `surfboard` versus `skis`, or `tv` versus `laptop`.
- The aggregate tables expose the boolean fields `label` and `ground_truth_rating`, which are the paper-facing annotations used for modeling and evaluation.

This means the repository should be read as a multimodal behavioral dataset for image-caption disagreement analysis rather than as an image-only or gaze-only benchmark.

## Repository Structure

```text
.
├── Facial_Data_Features_Extracted.csv
├── Gaze_Data_Features_Extracted_All.csv
├── Gaze_Data_Features_Extracted_3s.csv
├── Gaze_Data_Features_Extracted_11s.csv
├── AOI_Data/
│   ├── A/
│   └── B/
├── Facial_Data_AUs_Extracted/
├── Facial_Data_AUs_Heatmap/
├── Facial_Data_Emotions_Extracted/
├── Gaze_Data_Events_Extracted/
├── Gaze_Data_Heatmap/
├── Gaze_Data_Scanpath/
└── scripts/
```

## Modalities and Files

### Aggregate Feature Tables

- `Gaze_Data_Features_Extracted_All.csv`: one row per trial with gaze-derived summary features such as fixation counts, fixation duration statistics, saccade statistics, scanpath measures, pupil statistics, AOI transitions, `label`, and `ground_truth_rating`.
- `Gaze_Data_Features_Extracted_3s.csv`: gaze features aggregated over 3-second windows.
- `Gaze_Data_Features_Extracted_11s.csv`: gaze features aggregated over 11-second windows.
- `Facial_Data_Features_Extracted.csv`: one row per trial with aggregate statistics computed from facial action unit time series.

### Facial Data

- `Facial_Data_AUs_Extracted/`: 4,092 per-entry CSV files containing frame-level facial action unit intensities.
- `Facial_Data_Emotions_Extracted/`: 4,092 per-entry CSV files containing frame-level emotion probabilities (`anger`, `disgust`, `fear`, `happiness`, `sadness`, `surprise`, `neutral`).
- `Facial_Data_AUs_Heatmap/`: 4,092 PNG visualizations of action unit activity.

### Gaze Data

- `Gaze_Data_Events_Extracted/`: 4,092 per-entry CSV files with timestamped gaze samples, fixation metadata, pupil measurements, event labels, and AOI assignments.
- `Gaze_Data_Heatmap/`: 4,092 PNG gaze heatmaps.
- `Gaze_Data_Scanpath/`: 4,092 PNG scanpath visualizations.

### AOI Definitions

`AOI_Data/A/` and `AOI_Data/B/` contain AOI layouts keyed by zero-padded stimulus IDs such as `000000102281.csv`.

Each AOI CSV contains rectangular regions with the schema:

```text
aoi_type,aoi,pos_x,pos_y,width,height
```

The AOIs include:

- A single `image` region covering the visual stimulus.
- Word-level AOIs describing the caption variant shown with that image.

The `A` and `B` folders provide paired AOI definitions for the same image IDs, allowing the repository to distinguish between two caption variants linked to the same underlying stimulus image. In many cases those variants differ by one semantically critical word, which is consistent with the disagreement-oriented task setup used in the paper.

The AOI directories are intended to store the annotation CSVs only. The underlying stimulus images can be restored on demand with the download helper script described below.

## Using the Dataset

Typical entry points are:

- Use the root-level aggregate CSV files when you need one row per trial for modeling or exploratory analysis.
- Use the per-entry facial and gaze folders when you need time-resolved signals tied to a specific image-caption judgment.
- Use `AOI_Data` when you need the image region and word-level caption regions used for gaze/AOI analysis.
- Use the PNG folders when you want qualitative inspection of the recorded behavior and derived features.

## Downloading MS COCO Images

The repository stores derived multimodal signals and AOI metadata, but it does not redistribute the raw MS COCO images. To restore the stimulus images referenced by `AOI_Data`, use the helper script in `scripts/`:

```bash
python3 scripts/download_coco_images.py
```

By default, the script:

- scans `AOI_Data/A/*.csv` and `AOI_Data/B/*.csv`
- extracts the unique AOI image IDs from those CSV filenames
- tries standard COCO 2014 and 2017 split URLs until it resolves the image
- downloads one image per unique stimulus ID
- writes a manifest that maps every AOI CSV entry back to the downloaded image path

Example with an explicit split mapping file:

```bash
python3 scripts/download_coco_images.py \
        --mapping-csv path/to/coco_split_mapping.csv \
        --output-dir mscoco_images \
        --manifest-path mscoco_images/manifest.csv
```

The optional mapping file should contain at least:

```text
image_id,split
```

or:

```text
stimuli,split
```

## Citation

If you use this dataset, please cite our CHI 2026 paper:

```bibtex
@inproceedings{disagreement-detection-chi26,
        author       =  {Mohamed Selim, Abdulrahman and Bhatti, Omair Shahzad and Gomaa, Amr and Barz, Michael and Sonntag, Daniel},
        title = {Do You (Dis)agree With Me? Modelling Implicit User Disagreement in Human–AI Interaction Using Gaze Data},
        booktitle    = {Proceedings of the 2026 CHI Conference on Human Factors in Computing Systems (CHI '26)},
        year         = {2026},
        isbn         = {979-8-4007-2278-3/2026/04},
        doi          = {10.1145/3772318.3790594},
        address      = {Barcelona, Spain},
        month        = {April 13--17},
        publisher = {Association for Computing Machinery (ACM)},
        copyright    = {CC BY-NC-ND 4.0}
}
```

## License

This dataset is licensed under the [Creative Commons Attribution-NonCommercial-NoDerivatives 4.0 International License (CC BY-NC-ND 4.0)](https://creativecommons.org/licenses/by-nc-nd/4.0/).
