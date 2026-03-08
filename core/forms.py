from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import (
    AuthenticationForm,
    PasswordChangeForm,
    PasswordResetForm,
    SetPasswordForm,
    UserCreationForm,
)

User = get_user_model()

INPUT_CSS = (
    "w-full bg-black/30 border border-white/[0.05] rounded-[10px] "
    "px-4 py-3 text-[0.85rem] text-[#fafafa] font-sans placeholder-[#3d3a36] "
    "focus:border-copper/25 focus:outline-none focus:ring-1 focus:ring-copper/10 "
    "transition-all duration-300"
)


class SignUpForm(UserCreationForm):
    first_name = forms.CharField(
        max_length=150,
        widget=forms.TextInput(
            attrs={
                "class": INPUT_CSS,
                "placeholder": "First name",
                "autocomplete": "given-name",
            }
        ),
    )
    last_name = forms.CharField(
        max_length=150,
        widget=forms.TextInput(
            attrs={
                "class": INPUT_CSS,
                "placeholder": "Last name",
                "autocomplete": "family-name",
            }
        ),
    )

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("first_name", "last_name", "username", "email")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].widget.attrs.update(
            {"class": INPUT_CSS, "placeholder": "Username"}
        )
        self.fields["email"].widget.attrs.update(
            {"class": INPUT_CSS, "placeholder": "Email address"}
        )
        self.fields["email"].required = True
        self.fields["password1"].widget.attrs.update(
            {"class": INPUT_CSS, "placeholder": "Password"}
        )
        self.fields["password2"].widget.attrs.update(
            {"class": INPUT_CSS, "placeholder": "Confirm password"}
        )


class SignInForm(AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].widget.attrs.update(
            {"class": INPUT_CSS, "placeholder": "Username"}
        )
        self.fields["password"].widget.attrs.update(
            {"class": INPUT_CSS, "placeholder": "Password"}
        )


class TidalPasswordResetForm(PasswordResetForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["email"].widget.attrs.update(
            {"class": INPUT_CSS, "placeholder": "Email address"}
        )


class TidalSetPasswordForm(SetPasswordForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["new_password1"].widget.attrs.update(
            {"class": INPUT_CSS, "placeholder": "New password"}
        )
        self.fields["new_password2"].widget.attrs.update(
            {"class": INPUT_CSS, "placeholder": "Confirm new password"}
        )


SELECT_CSS = (
    "w-full bg-black/30 border border-white/[0.05] rounded-[10px] "
    "px-4 py-3 text-[0.85rem] text-[#fafafa] font-sans "
    "focus:border-copper/25 focus:outline-none focus:ring-1 focus:ring-copper/10 "
    "transition-all duration-300 appearance-none"
)


class ProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ("first_name", "last_name", "currency", "timezone")
        widgets = {
            "first_name": forms.TextInput(
                attrs={"class": INPUT_CSS, "placeholder": "First name"}
            ),
            "last_name": forms.TextInput(
                attrs={"class": INPUT_CSS, "placeholder": "Last name"}
            ),
            "currency": forms.Select(attrs={"class": SELECT_CSS}),
            "timezone": forms.Select(attrs={"class": SELECT_CSS}),
        }


class TidalPasswordChangeForm(PasswordChangeForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["old_password"].widget.attrs.update(
            {"class": INPUT_CSS, "placeholder": "Current password"}
        )
        self.fields["new_password1"].widget.attrs.update(
            {"class": INPUT_CSS, "placeholder": "New password"}
        )
        self.fields["new_password2"].widget.attrs.update(
            {"class": INPUT_CSS, "placeholder": "Confirm new password"}
        )
