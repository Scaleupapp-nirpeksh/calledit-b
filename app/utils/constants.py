from enum import Enum


# --- Match Status ---
class MatchStatus(str, Enum):
    UPCOMING = "upcoming"
    TOSS = "toss"
    LIVE_1ST = "live_1st"
    INNINGS_BREAK = "innings_break"
    LIVE_2ND = "live_2nd"
    COMPLETED = "completed"
    ABANDONED = "abandoned"


# --- Prediction Types ---
class PredictionType(str, Enum):
    BALL = "ball"
    OVER = "over"
    MILESTONE = "milestone"
    MATCH_WINNER = "match_winner"


# --- Ball Outcomes (7 classes) ---
class BallOutcome(str, Enum):
    DOT = "dot"
    ONE = "1"
    TWO = "2"
    THREE = "3"
    FOUR = "4"
    SIX = "6"
    WICKET = "wicket"


# --- Scoring Points ---
BALL_CORRECT_POINTS = 10
OVER_EXACT_POINTS = 25
OVER_CLOSE_POINTS = 10   # within ±3
OVER_CLOSE_RANGE = 3
MILESTONE_CORRECT_POINTS = 50
MATCH_WINNER_POINTS = 100

# --- Streaks ---
STREAK_THRESHOLDS = {
    3: 1.5,
    5: 2.0,
    10: 3.0,
}

# --- Confidence Boost ---
CONFIDENCE_BOOSTS_PER_MATCH = 3
CONFIDENCE_BOOST_MULTIPLIER = 2.0

# --- Clutch Mode ---
CLUTCH_OVER_START = 15
CLUTCH_OVER_END = 20
CLUTCH_MULTIPLIER = 2.0

# --- Prediction Window ---
PREDICTION_WINDOW_SECONDS = 15

# --- Match Winner ---
MAX_WINNER_CHANGES = 2

# --- Leagues ---
MAX_LEAGUE_MEMBERS = 50

# --- Notifications ---
NOTIFICATION_TTL_DAYS = 30

# --- IPL Teams ---
IPL_TEAMS = {
    "CSK": "Chennai Super Kings",
    "MI": "Mumbai Indians",
    "RCB": "Royal Challengers Bengaluru",
    "KKR": "Kolkata Knight Riders",
    "DC": "Delhi Capitals",
    "PBKS": "Punjab Kings",
    "RR": "Rajasthan Royals",
    "SRH": "Sunrisers Hyderabad",
    "GT": "Gujarat Titans",
    "LSG": "Lucknow Super Giants",
}

# --- Badge Definitions ---
BADGES = {
    "first_prediction": {
        "name": "First Call",
        "description": "Made your first prediction",
        "icon": "trophy",
    },
    "streak_5": {
        "name": "On Fire",
        "description": "Got 5 predictions correct in a row",
        "icon": "fire",
    },
    "streak_10": {
        "name": "Unstoppable",
        "description": "Got 10 predictions correct in a row",
        "icon": "lightning",
    },
    "century": {
        "name": "Century Maker",
        "description": "Scored 100+ points in a single match",
        "icon": "100",
    },
    "clutch_master": {
        "name": "Clutch Master",
        "description": "Got 5 clutch mode predictions correct",
        "icon": "target",
    },
    "match_winner_3": {
        "name": "Oracle",
        "description": "Predicted match winner correctly 3 times",
        "icon": "crystal_ball",
    },
    "league_creator": {
        "name": "League Founder",
        "description": "Created your first league",
        "icon": "crown",
    },
    "social_sharer": {
        "name": "Show Off",
        "description": "Shared your first scorecard",
        "icon": "share",
    },
    "referral_1": {
        "name": "Recruiter",
        "description": "Referred your first friend",
        "icon": "handshake",
    },
    "matches_10": {
        "name": "Regular",
        "description": "Played in 10 matches",
        "icon": "calendar",
    },
    "matches_50": {
        "name": "Veteran",
        "description": "Played in 50 matches",
        "icon": "medal",
    },
    "top_10": {
        "name": "Elite",
        "description": "Finished in the top 10 of a match leaderboard",
        "icon": "star",
    },
}

# --- Milestone Types ---
class MilestoneType(str, Enum):
    BATTER_50 = "batter_50"
    BATTER_100 = "batter_100"
    BOWLER_3W = "bowler_3w"
    BOWLER_5W = "bowler_5w"
    TEAM_200 = "team_200"

# --- Innings ---
class InningsNumber(int, Enum):
    FIRST = 1
    SECOND = 2

# --- Match Phases ---
class MatchPhase(str, Enum):
    POWERPLAY = "powerplay"       # overs 1-6
    MIDDLE = "middle"             # overs 7-14
    DEATH = "death"               # overs 15-20
