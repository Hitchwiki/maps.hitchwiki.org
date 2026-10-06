from enum import Enum

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
    unsolicited = "unsolicited"


class Signal(BaseModel, use_enum_values=True):
    methods: list[MethodEnum]
    sign_content: str | None = None
    sign_languages: list[str] | None = None
    asking_content: str | None = None
    asking_languages: list[str] | None = None
    total_solicited: int | None = None
    duration: str | None = None


class ReasonEnum(str, Enum):
    holiday = "holiday"
    commute = "commute"
    business = "business"
    recreational = "recreational"
    # Local extension, not (yet) in the upstream standard: running errands is neither a
    # commute nor business nor leisure, and it is one of the commonest short local trips
    # a hitchhiker gets picked up on. Same value on both reason enums so the two answers
    # to "why was this trip happening" stay comparable.
    errands = "errands"


class Ride(BaseModel, use_enum_values=True):
    vehicle_destination: Location | None = None
    reasons: list[ReasonEnum] | None = None


class GenderEnum(str, Enum):
    male = "male"
    female = "female"
    non_binary = "non_binary"
    prefer_not_to_say = "prefer_not_to_say"


class Person(BaseModel, use_enum_values=True):
    origin_location: str | None = None
    origin_country: str | None = None
    year_of_birth: int | None = None
    gender: GenderEnum | None = None
    languages: list[str] | None = None
    was_driver: bool | None = None


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
    reasons_to_pick_up: list[ReasonToPickUpEnum] | None = None
    would_ride_again: bool | None = None  # Whether the hitchhiker would take a ride with this occupant again
    positive_experiences: list[PositiveExperienceEnum] | None = None
    negative_experiences: list[NegativeExperienceEnum] | None = None


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
    make: str | None = None
    model: str | None = None
    license_plate_country: str | None = None  # ISO 3166-1 alpha-2
    license_plate_identifier: str | None = None


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
    errands = "errands"  # Local extension, see ReasonEnum.errands.


class Hitchhiker(Person, use_enum_values=True):
    nickname: str | None = None  # Nickname of the hitchhiker. Assumed unique within the data source.
    hitchhiking_since: int | None = None  # The year the person hitchhiked for the first time.
    reasons_to_hitchhike: list[ReasonToHitchhikeEnum] | None = None  # Reasons for a specific hitchhiking ride.


class GiftKindEnum(str, Enum):
    money = "money"
    food = "food"
    goods = "goods"


class Gift(BaseModel, use_enum_values=True):
    kind: GiftKindEnum = Field(...)
    description: str | None = None
    price: tuple[float, str] | None = None  # [amount, currency]


class DeclinedRideReasonEnum(str, Enum):
    wrong_direction = "wrong_direction"
    too_short = "too_short"
    too_long = "too_long"
    risk_concern = "risk_concern"
    safety_concern = "safety_concern"
    space_missing = "space_missing"
    too_slow = "too_slow"


class DeclinedRide(BaseModel, use_enum_values=True):
    destination: Location | None = None
    reasons: list[DeclinedRideReasonEnum] | None = None


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
    reasons: list[NoRideReasonEnum] | None = None


class Stop(BaseModel):
    # Optional, not Field(...): an intermediate stop the hitchhiker names ("onsen",
    # "grandparents' house") but never pinned a coordinate for is still worth recording
    # -- pickup and destination stops always set this, only a mid-journey one may omit it.
    location: Location | None = None
    # Not yet in the upstream hitchhiking-data-standard (proposed, not merged --
    # Hitchwiki/hitchhiking-data-standard#54) but the read side (ride_facts.stop_facts)
    # already expects it, so this vendored copy carries it now rather than waiting.
    label: str | None = None
    arrival_time: str | None = None  # RFC 9557 format
    departure_time: str | None = None  # RFC 9557 format
    waiting_duration: str | None = None  # ISO 8601 duration format


class HitchhikingRecord(BaseModel):
    version: str = Field(...)
    stops: list[Stop] = Field(..., min_items=1)
    rating: int | None = Field(None, ge=1, le=5)
    hitchhikers: list[Hitchhiker] = Field(..., min_items=1)
    comment: str | None = None
    signals: list[Signal] | None = None
    occupants: list[Occupant] | None = None
    mode_of_transportation: ModeOfTranportation | None = None
    ride: Ride | None = None
    declined_rides: list[DeclinedRide] | None = None
    no_ride: NoRide | None = None  # Present when the hitchhiker gave up at the spot without getting a ride
    images: list[str] | None = None  # URLs to images taken during the ride
    source: str = Field(...)
    license: str = Field(...)
    submission_time: str | None = None  # RFC 9557 format
