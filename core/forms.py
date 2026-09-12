"""
core — forms.
"""

from django import forms


class NewsletterForm(forms.Form):
    """The footer "stay in the loop" signup (single email field)."""

    email = forms.EmailField(
        max_length=254,
        label='Email address',
        widget=forms.EmailInput(
            attrs={
                'class': 'form-control form-ss',
                'placeholder': 'Your email address',
                'aria-label': 'Email address',
            }
        ),
    )
