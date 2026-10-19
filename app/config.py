# All the app settings are here. Values are read from the .env file if it exists,
# otherwise the defaults below are used so the app still runs locally.
import os

from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./bus_booking.db")

# JWT stuff
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-change-me-before-deploying-123")
ALGORITHM = "HS256"
TOKEN_EXPIRE_MINUTES = int(os.getenv("TOKEN_EXPIRE_MINUTES", "60"))

# Booking rules
SEAT_HOLD_MINUTES = int(os.getenv("SEAT_HOLD_MINUTES", "10"))  # how long seats stay held before payment
MAX_SEATS_PER_BOOKING = int(os.getenv("MAX_SEATS_PER_BOOKING", "6"))

# Refunds: cancel more than FREE_CANCEL_HOURS before departure -> early %, otherwise late %
FREE_CANCEL_HOURS = int(os.getenv("FREE_CANCEL_HOURS", "24"))
REFUND_PERCENT_EARLY = int(os.getenv("REFUND_PERCENT_EARLY", "90"))
REFUND_PERCENT_LATE = int(os.getenv("REFUND_PERCENT_LATE", "50"))

# Everything is stored in UTC. Search dates are in local time, so we need the offset.
# 330 minutes = IST (+5:30)
LOCAL_TIME_OFFSET_MINUTES = int(os.getenv("LOCAL_TIME_OFFSET_MINUTES", "330"))
