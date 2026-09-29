# validation/

`python -m taxlobby build` writes `data/processed/validation_sample.csv`: 300 randomly drawn
disclosed government posts with the classifier's code (`machine_code`).

1. Copy it here, fill in `hand_code` (tax / tax_member_staff / other / intern_only / non_government / none).
2. Ideally have a second person code the same rows to report inter-coder agreement.
3. Report accuracy (share of rows where `hand_code == machine_code`) in the paper.

Keep the completed file here so the validation is part of the record.
