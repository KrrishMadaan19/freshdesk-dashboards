"""Freshdesk export column names, as one source of truth.

Every script that reads the raw export or the merged master dataset should
import its column names from here instead of hardcoding the string again --
if Freshdesk ever renames a column, this is the only place that needs to
change.
"""

TICKET_ID = "Ticket ID"
GROUP = "Group"
PARTNER_NAME = "Partner Name"
UTR = "UTR"

CREATED_TIME = "Created time"
RESOLVED_TIME = "Resolved time"
WHATSAPP_SURVEY_RECEIVED = "WhatsApp Survey Received"

INWARD_PAYMENT_GROUP_ASSIGNMENT = "Inward Payment Group Assignment"
SPARE_GROUP_ASSIGNMENT = "Spare Group Assignment"
REFUND_GROUP_ASSIGNMENT = "Refund Group Assignment"
REPLACEMENT_GROUP_ASSIGNMENT = "Replacement Group Assignment"
CLOSE_LOOPING_GROUP_ASSIGNMENT = "Close Looping Group Assignment"
SERVICE_PARTNER_ASSIGNED_DATE_STAMP = "Service Partner Assigned Date Stamp"
