"""
payments app — forms (PHASE 13: test-mode card payment).

The card form validates everything SERVER-SIDE. The customer types what
they like — the server decides whether it's a usable card:
    * card number: exactly 16 digits (spaces/dashes ignored)
    * expiry:      MM/YY, and not in the past (valid to the end of the month)
    * cvv:         3 or 4 digits
"""

import re

from django import forms

EXPIRY_RE = re.compile(r'^(0[1-9]|1[0-2])/\d{2}$')   # MM/YY


class TestCardForm(forms.Form):
    """A payment card, in TEST mode (no real charge is made)."""

    card_number = forms.CharField(
        label='Card number', max_length=19,
        widget=forms.TextInput(attrs={'autofocus': True}),
    )
    name = forms.CharField(
        label='Name on card', max_length=150,
        widget=forms.TextInput(attrs={'placeholder': 'As printed on the card'}),
    )
    expiry = forms.CharField(
        label='Expiry (MM/YY)', max_length=5,
        widget=forms.TextInput(attrs={'placeholder': '12/27'}),
    )
    cvv = forms.CharField(
        label='CVV', max_length=4,
        widget=forms.TextInput(attrs={'placeholder': '123'}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['card_number'].widget.attrs.update(
            {'placeholder': '4242 4242 4242 4242', 'inputmode': 'numeric'})
        self.fields['expiry'].widget.attrs.update(
            {'placeholder': '12/27', 'inputmode': 'numeric'})
        self.fields['cvv'].widget.attrs.update(
            {'placeholder': '123', 'inputmode': 'numeric'})

    # ------------------------- field cleans --------------------------------
    def clean_card_number(self):
        digits = re.sub(r'\D', '', self.cleaned_data['card_number'] or '')
        if len(digits) != 16:
            raise forms.ValidationError('Enter the 16-digit card number.')
        return digits

    def clean_expiry(self):
        value = (self.cleaned_data['expiry'] or '').strip()
        if not EXPIRY_RE.match(value):
            raise forms.ValidationError(
                'Enter the expiry as MM/YY, e.g. 12/27.'
            )
        month = int(value[:2])
        year = 2000 + int(value[3:])
        # A card stays valid through the END of its expiry month.
        from django.utils import timezone
        today = timezone.now().date()
        if (year, month) < (today.year, today.month):
            raise forms.ValidationError('This card has expired.')
        return value

    def clean_cvv(self):
        digits = re.sub(r'\D', '', self.cleaned_data['cvv'] or '')
        if len(digits) not in (3, 4):
            raise forms.ValidationError('CVV is 3 or 4 digits.')
        return digits
