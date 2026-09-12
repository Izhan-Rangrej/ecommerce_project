"""
customers app — forms (PHASE 8: registration, profile, addresses).

Everything here is validated SERVER-SIDE. Client-side tricks (required
attributes, pattern hints, live password strength meter) are a courtesy
only — the server is the single source of truth.
"""

import re

from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

from .models import Address

# Indian-style validation, kept deliberately simple and strict.
PINCODE_RE = re.compile(r'^\d{6}$')          # exactly 6 digits
PHONE_RE = re.compile(r'^\d{10,15}$')        # 10–15 digits (no +, spaces, dashes)


def clean_phone(value):
    """Strip non-digits and enforce 10–15 digits. Returns the clean digits."""
    digits = re.sub(r'\D', '', value or '')
    if not PHONE_RE.match(digits):
        raise forms.ValidationError(
            'Enter a valid phone number (10 to 15 digits).'
        )
    return digits


def clean_pincode(value):
    pin = (value or '').strip()
    if not PINCODE_RE.match(pin):
        raise forms.ValidationError('Enter a valid 6-digit PIN code.')
    return pin


# ---------------------------------------------------------------------------
# REGISTRATION
# ---------------------------------------------------------------------------
class RegisterForm(UserCreationForm):
    """
    Creates a new account.

    * username + two passwords come from UserCreationForm, which already
      runs Django's standard password validators (min 8 chars, not too
      common, not just numbers, not similar to the username) and the
      unique-username check.
    * email is required and must be unique — checked below, because the
      default User model does NOT enforce email uniqueness.
    """

    email = forms.EmailField(
        required=True,
        label='Email address',
        widget=forms.EmailInput(attrs={'autofocus': True}),
    )

    class Meta:
        model = User
        fields = ['username', 'email', 'password1', 'password2']

    def clean_email(self):
        email = (self.cleaned_data.get('email') or '').strip()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(
                'An account with this email already exists.'
            )
        return email


# ---------------------------------------------------------------------------
# PROFILE UPDATE
# ---------------------------------------------------------------------------
class ProfileUpdateForm(forms.ModelForm):
    """
    Update the account's details.

    It edits the User (name, email, username) AND two UserProfile fields
    (phone, date of birth) in one form — so it is a ModelForm for User
    plus two plain fields that the view saves on the profile object.
    """

    phone = forms.CharField(
        max_length=15, required=False,
        widget=forms.TextInput(attrs={'placeholder': 'e.g. 98765 43210'}),
    )
    date_of_birth = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date'}),
    )

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'username']
        labels = {'first_name': 'First name', 'last_name': 'Last name'}
        widgets = {
            'username': forms.TextInput(attrs={'autofocus': True}),
        }

    def clean_email(self):
        email = (self.cleaned_data.get('email') or '').strip()
        if not email:
            raise forms.ValidationError('Email address is required.')
        if User.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError(
                'This email is already in use by another account.'
            )
        return email

    def clean_username(self):
        username = (self.cleaned_data.get('username') or '').strip()
        if User.objects.filter(username__iexact=username).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError('This username is already taken.')
        return username

    def clean_phone(self):
        # Empty phone is allowed (the profile form tolerates "not yet set").
        value = (self.cleaned_data.get('phone') or '').strip()
        if not value:
            return ''
        return clean_phone(value)

    def save(self, commit=True):
        user = super().save(commit=commit)
        if commit:
            # The profile always exists (created by the post_save signal),
            # so this is a plain update.
            profile = user.profile
            profile.phone = self.cleaned_data.get('phone') or ''
            profile.date_of_birth = self.cleaned_data.get('date_of_birth')
            profile.save()
        return user


# ---------------------------------------------------------------------------
# ADDRESSES
# ---------------------------------------------------------------------------
class AddressForm(forms.ModelForm):
    """Add/edit a saved shipping address (label, contact, location)."""

    class Meta:
        model = Address
        fields = [
            'label', 'full_name', 'phone',
            'address_line_1', 'address_line_2',
            'city', 'state', 'pincode', 'country',
        ]
        widgets = {
            'label': forms.TextInput(attrs={'placeholder': "e.g. 'Home' or 'Office'"}),
            'address_line_2': forms.TextInput(attrs={'placeholder': 'Flat, street, area (optional)'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['phone'].help_text = '10–15 digits, used to coordinate delivery.'

    def clean_phone(self):
        return clean_phone(self.cleaned_data['phone'])

    def clean_pincode(self):
        return clean_pincode(self.cleaned_data['pincode'])
