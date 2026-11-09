from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User


class InscriptionForm(UserCreationForm):
    email = forms.EmailField(label="Adresse e-mail")
    first_name = forms.CharField(label="Prénom", max_length=150)

    class Meta:
        model = User
        fields = ["first_name", "username", "email"]
        labels = {"username": "Nom d'utilisateur"}

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Un compte existe déjà avec cette adresse e-mail.")
        return email
