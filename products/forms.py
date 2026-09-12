"""
PHASE 15 — forms for the products app.

ReviewForm is a ModelForm with a twist: the product is NOT a field (a
customer always reviews the product on the page they're looking at), so
it's passed in separately and pinned onto the instance in __init__.
Without that pin, form.save() would try to insert a review with
product=None and crash on the NOT NULL constraint.
"""
from django import forms

from .models import Review


class ReviewForm(forms.ModelForm):
    """The write-a-review form on the product detail page."""

    class Meta:
        model = Review
        fields = ['rating', 'comment']
        widgets = {
            'comment': forms.Textarea(
                attrs={
                    'rows': 3,
                    'maxlength': 1000,
                    'placeholder': 'What did you like or dislike? (optional)',
                }
            ),
        }

    def __init__(self, *args, product=None, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        # Pin product + author onto the instance so save() knows where
        # this review belongs (neither can be None after this).
        if product is not None:
            self.instance.product = product
        if user is not None:
            self.instance.user = user
        self.fields['rating'].label = 'Your rating'
        self.fields['comment'].label = 'Your review'
