"""Tabler/Bootstrap form-control classes for Django's bare `{{ field }}` rendering.

Django doesn't add Bootstrap's `form-control`/`form-select`/`form-check-input` classes on its own --
forms.py doesn't set them on every widget either, so this is applied at render time instead, once, here.
"""
from django import forms, template

register = template.Library()

_CHECK_WIDGETS = (forms.CheckboxInput, forms.CheckboxSelectMultiple, forms.RadioSelect)
_SELECT_WIDGETS = (forms.Select, forms.SelectMultiple)


@register.filter
def bootstrap_field(field):
    """Render a bound field with the Tabler/Bootstrap class its widget type needs, keeping any class already set."""
    widget = field.field.widget
    if isinstance(widget, _CHECK_WIDGETS):
        css = "form-check-input"
    elif isinstance(widget, _SELECT_WIDGETS):
        css = "form-select"
    else:
        css = "form-control"
    existing = widget.attrs.get("class", "")
    classes = f"{existing} {css}".strip() if existing and css not in existing.split() else (existing or css)
    return field.as_widget(attrs={**widget.attrs, "class": classes})
