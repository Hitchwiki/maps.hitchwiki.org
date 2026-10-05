from datetime import datetime

import pycountry
from flask_wtf import FlaskForm
from flask_wtf.file import FileField
from wtforms import BooleanField, FieldList, IntegerField, RadioField, SelectField, StringField, SubmitField
from wtforms.validators import Optional
from wtforms.widgets import NumberInput

from hitch.profile_links import MAX_LINKS


class CountrySelectField(SelectField):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.choices = [("", "None")] + [(country.name, country.name) for country in pycountry.countries]


class UserEditForm(FlaskForm):
    avatar_source = RadioField(
        "Profile picture",
        choices=[("none", "No profile picture"), ("upload", "Upload a picture"), ("gravatar", "Use Gravatar")],
        default="none",
    )
    avatar_image = FileField("Choose a picture", validators=[Optional()])
    gender = SelectField(
        "Gender",
        choices=[
            ("", "None"),
            ("Female", "Female"),
            ("Male", "Male"),
            ("Non-Binary", "Non-Binary"),
            ("Prefer not to say", "Prefer not to say"),
        ],
    )
    year_of_birth = IntegerField(
        "Year of Birth",
        widget=NumberInput(min=1900, max=datetime.now().year),
        validators=[Optional()],
    )
    hitchhiking_since = IntegerField(
        "Hitchhiking Since",
        widget=NumberInput(min=1900, max=datetime.now().year),
        validators=[Optional()],
    )
    origin_country = CountrySelectField("Where are you from?")
    origin_city = StringField("Which city are you from?", validators=[Optional()])
    current_country = CountrySelectField("Which country are you in right now?")
    current_city = StringField("Which city are you in right now?", validators=[Optional()])
    hitchwiki_username = StringField("Hitchwiki Username", validators=[Optional()], default=None)
    trustroots_username = StringField("Trustroots Username", validators=[Optional()], default=None)
    # Always MAX_LINKS inputs: validation and normalisation happen in the view
    # (profile_links.normalize_link), which accepts "instagram.com/me" without a scheme.
    profile_links = FieldList(StringField(validators=[Optional()]), min_entries=MAX_LINKS, max_entries=MAX_LINKS)
    email_notifications = BooleanField("Receive notifications and updates via email", default=True)
    nearby_hitchhikers_email = BooleanField("Email me about other hitchhikers who were close by", default=False)
    allow_messages = BooleanField("Let other hitchhikers message me (adds a Chat button to my profile)", default=True)
    message_email_notifications = BooleanField("Email me when I receive a new message", default=True)
    distance_unit = SelectField(
        "Distance units",
        choices=[("metric", "Metric (km)"), ("imperial", "Imperial (miles)")],
        default="metric",
    )
    submit = SubmitField("Submit")
