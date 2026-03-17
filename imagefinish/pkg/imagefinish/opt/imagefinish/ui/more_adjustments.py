"""Backward-compat re-export — all adjustments now live in core/adjustments/."""

from core.adjustments import (  # noqa: F401
    apply_exposure, ExposureDialog,
    apply_vibrance, VibranceDialog,
    apply_black_white, BlackWhiteDialog,
    apply_posterize, PosterizeDialog,
    apply_threshold, ThresholdDialog,
    apply_photo_filter, PhotoFilterDialog,
    apply_gradient_map, GradientMapDialog,
    apply_equalize,
    apply_shadows_highlights, ShadowsHighlightsDialog,
    apply_replace_color, ReplaceColorDialog,
    apply_channel_mixer, ChannelMixerDialog,
    apply_selective_color, SelectiveColorDialog,
    apply_match_color, MatchColorDialog,
    apply_color_lookup, ColorLookupDialog, parse_cube,
    apply_hdr_toning, HDRToningDialog,
)
