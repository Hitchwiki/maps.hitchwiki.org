from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Location(BaseModel):
    latitude: float
    longitude: float
    is_exact: bool


class MethodEnum(str, Enum):
    thumb = "thumb"
    waving = "waving"
    sign = "sign"
    asking = "asking"
    invited = "invited"
    prearranged = "prearranged"


class Signal(BaseModel, use_enum_values=True):
    methods: list[MethodEnum]
    sign_content: Optional[str] = None
    sign_languages: Optional[list[str]] = None
    asking_content: Optional[str] = None
    asking_languages: Optional[list[str]] = None
    total_solicited: Optional[int] = None
    duration: Optional[str] = None


class ReasonEnum(str, Enum):
    holiday = "holiday"
    commute = "commute"
    business = "business"
    recreational = "recreational"


class Ride(BaseModel, use_enum_values=True):
    vehicle_destination: Optional[Location] = None
    reasons: Optional[list[ReasonEnum]] = None


class GenderEnum(str, Enum):
    male = "male"
    female = "female"
    non_binary = "non_binary"
    prefer_not_to_say = "prefer_not_to_say"


class Person(BaseModel, use_enum_values=True):
    origin_location: Optional[str] = None
    origin_country: Optional[str] = None
    year_of_birth: Optional[int] = None
    gender: Optional[GenderEnum] = None
    languages: Optional[list[str]] = None
    was_driver: Optional[bool] = None


class ReasonToPickUpEnum(str, Enum):
    is_hitchhiker = "is_hitchhiker"
    was_hitchhiker = "was_hitchhiker"
    social_exchange = "social_exchange"
    cultural_exchange = "cultural_exchange"
    environmental = "environmental"
    wanted_driver = "wanted_driver"
    curiosity = "curiosity"
    hospitality_norm = "hospitality_norm"
    elevated_mood = "elevated_mood"
    nonthreatening_appearance = "nonthreatening_appearance"
    sympathy = "sympathy"
    safety_concern = "safety_concern"
    opposed = "opposed"

class PositiveExperienceEnum(str, Enum):
    friendly = "friendly"
    good_conversation = "good_conversation"
    helpful = "helpful"
    safe_driving = "safe_driving"
    generous = "generous"
    interesting = "interesting"
    felt_safe = "felt_safe"
    comfortable = "comfortable"


class NegativeExperienceEnum(str, Enum):
    unfriendly = "unfriendly"
    unsafe_driving = "unsafe_driving"
    uncomfortable = "uncomfortable"
    inappropriate_behavior = "inappropriate_behavior"
    intoxicated = "intoxicated"
    aggressive = "aggressive"
    expected_something_in_return = "expected_something_in_return"
    felt_unsafe = "felt_unsafe"

class Occupant(Person, use_enum_values=True):
    # Upstream narrowed this to a single enum; we keep a list because our driver-info
    # form is a multi-select and rides already published to Nostr carry lists here.
    reasons_to_pick_up: Optional[list[ReasonToPickUpEnum]] = None
    would_ride_again: Optional[bool] = None  # Whether the hitchhiker would take a ride with this occupant again
    positive_experiences: Optional[list[PositiveExperienceEnum]] = None
    negative_experiences: Optional[list[NegativeExperienceEnum]] = None


class KindEnum(str, Enum):
    car = "car"
    bus = "bus"
    van = "van"
    truck = "truck"
    motorbike = "motorbike"
    scooter = "scooter"
    taxi = "taxi"
    horse_cart = "horse-cart"
    train = "train"
    camper = "camper"
    tractor = "tractor"
    plane = "plane"
    ferry = "ferry"
    boat = "boat"


class ModeOfTranportation(BaseModel, use_enum_values=True):
    kind: KindEnum = Field(...)
    make: Optional[str] = None
    model: Optional[str] = None
    license_plate_country: Optional[str] = None  # ISO 3166-1 alpha-2
    license_plate_identifier: Optional[str] = None


class ReasonToHitchhikeEnum(str, Enum):
    commute = "commute"
    vacation = "vacation"
    sport = "sport"
    financial = "financial"
    social_exchange = "social_exchange"
    cultural_exchange = "cultural_exchange"
    recreational = "recreational"
    environmental = "environmental"
    fundraising = "fundraising"


class Hitchhiker(Person, use_enum_values=True):
    nickname: Optional[str] = None  # Nickname of the hitchhiker. Assumed unique within the data source.
    hitchhiking_since: Optional[int] = None  # The year the person hitchhiked for the first time.
    reasons_to_hitchhike: Optional[list[ReasonToHitchhikeEnum]] = None  # Reasons for a specific hitchhiking ride.


class GiftKindEnum(str, Enum):
    money = "money"
    food = "food"
    goods = "goods"


class Gift(BaseModel, use_enum_values=True):
    kind: GiftKindEnum = Field(...)
    description: Optional[str] = None
    price: Optional[tuple[float, str]] = None  # [amount, currency]


class DeclinedRideReasonEnum(str, Enum):
    wrong_direction = "wrong_direction"
    too_short = "too_short"
    too_long = "too_long"
    risk_concern = "risk_concern"
    safety_concern = "safety_concern"
    space_missing = "space_missing"
    too_slow = "too_slow"


class DeclinedRide(BaseModel, use_enum_values=True):
    destination: Optional[Location] = None
    reasons: Optional[list[DeclinedRideReasonEnum]] = None


class NoRideReasonEnum(str, Enum):
    waited_too_long = "waited_too_long"
    bad_weather = "bad_weather"
    darkness = "darkness"
    unsafe_location = "unsafe_location"
    poor_spot = "poor_spot"
    too_much_competition = "too_much_competition"
    changed_plans = "changed_plans"
    took_alternative_transport = "took_alternative_transport"
    gave_up = "gave_up"

class NoRide(BaseModel, use_enum_values=True):
    reasons: Optional[list[NoRideReasonEnum]] = None


class Stop(BaseModel):
    location: Location = Field(...)
    arrival_time: Optional[str] = None  # RFC 9557 format
    departure_time: Optional[str] = None  # RFC 9557 format
    waiting_duration: Optional[str] = None  # ISO 8601 duration format


class HitchhikingRecord(BaseModel):
    version: str = Field(...)
    stops: list[Stop] = Field(..., min_items=1)
    rating: Optional[int] = Field(None, ge=1, le=5)
    hitchhikers: list[Hitchhiker] = Field(..., min_items=1)
    comment: Optional[str] = None
    signals: Optional[list[Signal]] = None
    occupants: Optional[list[Occupant]] = None
    mode_of_transportation: Optional[ModeOfTranportation] = None
    ride: Optional[Ride] = None
    declined_rides: Optional[list[DeclinedRide]] = None
    no_ride: Optional[NoRide] = None  # Present when the hitchhiker gave up at the spot without getting a ride
    images: Optional[list[str]] = None  # URLs to images taken during the ride
    source: str = Field(...)
    license: str = Field(...)
    submission_time: Optional[str] = None  # RFC 9557 format
