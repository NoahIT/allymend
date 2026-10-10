from pataisa.fixers.edits import apply_edits, unified_diff
from pataisa.fixers.html_has_lang import check_language_tag, fix_html_has_lang
from pataisa.fixers.plan import FixOptions, plan_fixes

__all__ = [
    "FixOptions",
    "apply_edits",
    "check_language_tag",
    "fix_html_has_lang",
    "plan_fixes",
    "unified_diff",
]
