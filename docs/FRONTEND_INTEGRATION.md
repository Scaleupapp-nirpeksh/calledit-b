# CalledIt — Frontend Integration Guide

> **Everything your frontend team needs to build the CalledIt app.**
> Base URL: `http://localhost:8000` (local) → `https://api.calledit.in` (production on EC2)
> All API routes are prefixed with `/api/v1`

---

## Table of Contents

1. [Authentication](#1-authentication)
2. [User Management](#2-user-management)
3. [Matches](#3-matches)
4. [Predictions](#4-predictions)
5. [Leaderboards](#5-leaderboards)
6. [Leagues](#6-leagues)
7. [Competitions](#7-competitions)
8. [AI & ML Features](#8-ai--ml-features)
9. [Social Features](#9-social-features)
10. [Admin Endpoints](#10-admin-endpoints)
11. [WebSocket (Real-Time)](#11-websocket-real-time)
12. [Scoring System](#12-scoring-system)
13. [Badges](#13-badges)
14. [Constants & Enums](#14-constants--enums)
15. [Error Handling](#15-error-handling)
16. [Complete User Flow](#16-complete-user-flow)

---

## 1. Authentication

All authenticated endpoints require: `Authorization: Bearer <access_token>`

### POST /api/v1/auth/otp/send

Send OTP to phone number via Twilio SMS.

**Request:**
```json
{
  "phone": "+919876543210"
}
```

**Response (200):**
```json
{
  "message": "OTP sent successfully"
}
```

**Notes:**
- Phone must be E.164 format (+ country code + number)
- Rate limited: 5 OTPs per minute per IP
- OTP expires in 5 minutes
- In dev mode, OTP is logged to server console (no SMS sent)

---

### POST /api/v1/auth/otp/verify

Verify OTP and receive JWT tokens. Creates user account if first login.

**Request:**
```json
{
  "phone": "+919876543210",
  "otp": "123456"
}
```

**Response (200):**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 900,
  "is_new_user": true
}
```

**Notes:**
- `expires_in` is in seconds (900 = 15 minutes for access token)
- `is_new_user: true` → redirect to onboarding screen
- `is_new_user: false` → redirect to home/matches screen
- Refresh token valid for 30 days

**JWT Payload (decoded):**
```json
{
  "sub": "user_nanoid_abc123",
  "type": "access",
  "exp": 1735689600
}
```

---

### POST /api/v1/auth/refresh

Get new token pair using refresh token. Call this when access token expires.

**Request:**
```json
{
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

**Response (200):** Same as `/otp/verify`

**Recommended flow:**
1. Store both tokens in secure storage
2. Use access token for all API calls
3. When you get a 401, call `/auth/refresh`
4. If refresh also fails → redirect to login

---

### POST /api/v1/auth/logout

Revoke refresh token. Requires auth.

**Response (200):**
```json
{
  "message": "Logged out successfully"
}
```

---

## 2. User Management

### GET /api/v1/users/me

Get current authenticated user's full profile.

**Response (200):**
```json
{
  "id": "usr_abc123xyz",
  "phone_masked": "+91XXXX****10",
  "username": "john_doe",
  "display_name": "John Doe",
  "avatar_url": "https://calledit-assets.s3.ap-south-1.amazonaws.com/avatars/abc.jpg",
  "favourite_team": "CSK",
  "favourite_players": ["MS Dhoni", "Ravindra Jadeja"],
  "referral_code": "JOHN7A3B",
  "stats": {
    "total_predictions": 245,
    "correct_predictions": 152,
    "accuracy": 62.04,
    "total_points": 5240,
    "current_streak": 3,
    "best_streak": 12,
    "matches_played": 15,
    "clutch_correct": 8,
    "match_winners_correct": 4
  },
  "badges": ["first_prediction", "streak_5", "streak_10", "century", "matches_10"],
  "is_onboarded": true,
  "created_at": "2026-02-15T10:30:00Z",
  "updated_at": "2026-02-21T14:45:30Z"
}
```

---

### PATCH /api/v1/users/me

Update profile. All fields optional — only send what changed.

**Request:**
```json
{
  "username": "new_username",
  "display_name": "New Display Name",
  "avatar_url": "https://...",
  "favourite_team": "MI",
  "favourite_players": ["Hardik Pandya", "Jasprit Bumrah"]
}
```

**Response (200):** Updated user object (same shape as GET /me)

**Errors:**
- 409: Username already taken

---

### POST /api/v1/users/me/onboarding

Complete onboarding for new users. Sets `is_onboarded: true`.

**Request:**
```json
{
  "username": "john_doe",
  "display_name": "John Doe",
  "favourite_team": "CSK",
  "favourite_players": ["MS Dhoni"],
  "referral_code_used": "FRIEND7A3B"
}
```

**Response (200):** Updated user object with `is_onboarded: true`

**Notes:**
- `username` is required and must be unique
- `display_name` is required
- `favourite_team` and `favourite_players` are optional
- `referral_code_used` is optional — if valid, the referrer gets a "Recruiter" badge
- After this call succeeds, redirect user to home screen

---

### GET /api/v1/users/{user_id}

Get any user's public profile.

**Response (200):** Same shape as `/me` (phone is masked)

---

### GET /api/v1/users/{user_id}/predictions

Get a user's prediction history.

**Query params:**
| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `match_id` | string | — | Filter to specific match |

**Response (200):**
```json
{
  "predictions": [
    {
      "id": "pred_abc123",
      "user_id": "usr_abc123xyz",
      "match_id": "match_001",
      "type": "ball",
      "innings": 1,
      "over": 5,
      "ball": 3,
      "ball_key": "1.5.3",
      "prediction": "4",
      "confidence_boost": true,
      "is_resolved": true,
      "is_correct": true,
      "actual_outcome": "4",
      "base_points": 10,
      "streak_multiplier": 1.5,
      "confidence_multiplier": 2.0,
      "clutch_multiplier": 1.0,
      "total_points": 30,
      "created_at": "2026-02-21T20:15:00Z",
      "resolved_at": "2026-02-21T20:15:45Z"
    }
  ],
  "total": 23
}
```

---

## 3. Matches

### GET /api/v1/matches

List matches with filters.

**Query params:**
| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `status` | string | — | Filter: `upcoming`, `toss`, `live_1st`, `innings_break`, `live_2nd`, `completed`, `abandoned` |
| `date` | string | — | Filter by date: `YYYY-MM-DD` |
| `team` | string | — | Filter by team name or code |
| `competition_id` | string | — | Filter by competition |
| `limit` | int | 20 | Results per page (1-50) |
| `offset` | int | 0 | Pagination offset |

**Response (200):**
```json
{
  "matches": [
    {
      "id": "match_abc123",
      "cricapi_id": "cricapi_12345",
      "name": "CSK vs MI - IPL 2026",
      "match_type": "T20",
      "status": "live_1st",
      "venue": "MA Chidambaram Stadium, Chennai",
      "date": "2026-03-26T19:30:00+05:30",
      "team1": "Chennai Super Kings",
      "team2": "Mumbai Indians",
      "team1_code": "CSK",
      "team2_code": "MI",
      "toss_winner": "Mumbai Indians",
      "toss_decision": "bat",
      "innings": [
        {
          "innings_number": 1,
          "batting_team": "Mumbai Indians",
          "bowling_team": "Chennai Super Kings",
          "score": 145,
          "wickets": 3,
          "overs": 15.3,
          "run_rate": 9.35
        },
        {
          "innings_number": 2,
          "batting_team": "Chennai Super Kings",
          "bowling_team": "Mumbai Indians",
          "score": 0,
          "wickets": 0,
          "overs": 0.0,
          "run_rate": 0.0,
          "target": null,
          "required_rate": null
        }
      ],
      "winner": null,
      "result_text": null,
      "competition_id": "comp_ipl_2026",
      "ai_preview": "A blockbuster IPL opener awaits...",
      "prediction_window_open": true,
      "current_innings": 1,
      "current_over": 16,
      "current_ball": 1,
      "win_probability_timeline": [],
      "created_at": "2026-03-20T10:00:00Z",
      "updated_at": "2026-03-26T20:45:30Z"
    }
  ],
  "total": 74
}
```

---

### GET /api/v1/matches/live

Get only live matches. No query params needed.

**Response:** Same shape as `/matches` list, filtered to status `live_1st` or `live_2nd`.

---

### GET /api/v1/matches/{match_id}

Get full details for a single match.

**Response (200):** Single match object (same shape as list item).

---

### GET /api/v1/matches/{match_id}/scorecard

Get full ball-by-ball scorecard.

**Response (200):**
```json
{
  "match_id": "match_abc123",
  "innings": [
    {
      "innings_number": 1,
      "batting_team": "Mumbai Indians",
      "bowling_team": "Chennai Super Kings",
      "score": 185,
      "wickets": 6,
      "overs": 20.0,
      "run_rate": 9.25
    }
  ],
  "ball_log": [
    {
      "ball_key": "1.1.1",
      "innings": 1,
      "over": 1,
      "ball": 1,
      "batter": "Rohit Sharma",
      "bowler": "Deepak Chahar",
      "non_striker": "Ishan Kishan",
      "outcome": "1",
      "batter_runs": 1,
      "extras": 0,
      "total_runs": 1,
      "is_wicket": false,
      "wicket_kind": null,
      "player_out": null
    },
    {
      "ball_key": "1.1.2",
      "innings": 1,
      "over": 1,
      "ball": 2,
      "batter": "Ishan Kishan",
      "bowler": "Deepak Chahar",
      "non_striker": "Rohit Sharma",
      "outcome": "wicket",
      "batter_runs": 0,
      "extras": 0,
      "total_runs": 0,
      "is_wicket": true,
      "wicket_kind": "caught",
      "player_out": "Ishan Kishan"
    }
  ]
}
```

---

### GET /api/v1/matches/{match_id}/timeline

Get ball-by-ball timeline for a specific innings.

**Query params:**
| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `innings` | int | 1 | Innings number (1 or 2) |

**Response (200):**
```json
{
  "match_id": "match_abc123",
  "innings": 1,
  "balls": [ ...ball_log entries for that innings... ]
}
```

---

### GET /api/v1/matches/{match_id}/win-probability

Get ML-predicted win probability for both teams.

**Response (200):**
```json
{
  "match_id": "match_abc123",
  "team1": "Chennai Super Kings",
  "team2": "Mumbai Indians",
  "probabilities": {
    "Chennai Super Kings": 0.65,
    "Mumbai Indians": 0.35
  },
  "model_version": "v2"
}
```

---

## 4. Predictions

All prediction endpoints require authentication.

### 4 Prediction Types

| Type | Endpoint | Points | Description |
|------|----------|--------|-------------|
| Ball | `POST /predictions/ball` | 10 pts | Predict next ball outcome |
| Over | `POST /predictions/over` | 25 pts (exact) / 10 pts (±3) | Predict total runs in an over |
| Milestone | `POST /predictions/milestone` | 50 pts | Predict player/team milestones |
| Match Winner | `POST /predictions/match-winner` | 100 pts | Predict match winner |

---

### POST /api/v1/predictions/ball

Predict the outcome of the next ball.

**Request:**
```json
{
  "match_id": "match_abc123",
  "innings": 1,
  "over": 5,
  "ball": 3,
  "prediction": "4",
  "confidence_boost": false
}
```

| Field | Type | Required | Validation |
|-------|------|----------|------------|
| `match_id` | string | yes | Match must be live |
| `innings` | int | yes | 1 or 2 |
| `over` | int | yes | 1-20 |
| `ball` | int | yes | 1-8 (includes extras) |
| `prediction` | string | yes | One of: `"dot"`, `"1"`, `"2"`, `"3"`, `"4"`, `"6"`, `"wicket"` |
| `confidence_boost` | bool | no | Default false. Max 3 per match. Doubles points if correct. |

**Response (200):**
```json
{
  "prediction": {
    "id": "pred_xyz789",
    "user_id": "usr_abc123",
    "match_id": "match_abc123",
    "type": "ball",
    "innings": 1,
    "over": 5,
    "ball": 3,
    "ball_key": "1.5.3",
    "prediction": "4",
    "confidence_boost": false,
    "is_resolved": false,
    "is_correct": null,
    "actual_outcome": null,
    "base_points": 0,
    "streak_multiplier": 1.0,
    "confidence_multiplier": 1.0,
    "clutch_multiplier": 1.0,
    "total_points": 0,
    "created_at": "2026-03-26T20:15:00Z",
    "resolved_at": null
  }
}
```

**Errors:**
- 400: Match not live / Prediction window closed / Duplicate prediction
- 400: Max 3 confidence boosts already used

**Important timing:** The prediction window opens for 15 seconds before each ball. Listen for the `prediction_window` WebSocket event to know when the window opens/closes.

---

### POST /api/v1/predictions/over

Predict total runs scored in an over.

**Request:**
```json
{
  "match_id": "match_abc123",
  "innings": 1,
  "over": 5,
  "predicted_runs": 8
}
```

| Field | Type | Required | Validation |
|-------|------|----------|------------|
| `predicted_runs` | int | yes | 0-50 |

**Scoring:** Exact match = 25 pts, within ±3 runs = 10 pts, otherwise 0.

---

### POST /api/v1/predictions/milestone

Predict player/team milestones.

**Request:**
```json
{
  "match_id": "match_abc123",
  "milestone_type": "batter_50",
  "player_name": "Rohit Sharma",
  "will_achieve": true
}
```

| Field | Type | Required | Values |
|-------|------|----------|--------|
| `milestone_type` | string | yes | `"batter_50"`, `"batter_100"`, `"bowler_3w"`, `"bowler_5w"`, `"team_200"` |
| `player_name` | string | yes | Player's full name |
| `will_achieve` | bool | yes | true = will achieve, false = won't |

**Scoring:** 50 pts if correct.

---

### POST /api/v1/predictions/match-winner

Predict the match winner. Can be changed up to 2 times.

**Request:**
```json
{
  "match_id": "match_abc123",
  "predicted_winner": "Chennai Super Kings"
}
```

| Field | Type | Required | Validation |
|-------|------|----------|------------|
| `predicted_winner` | string | yes | Must be one of the two teams in the match |

**Scoring:** 100 pts if correct. Can update max 2 times per match.

---

### GET /api/v1/predictions/match/{match_id}

Get all of the current user's predictions for a match.

**Response (200):**
```json
{
  "predictions": [ ...prediction objects... ],
  "total": 23
}
```

---

### GET /api/v1/predictions/match/{match_id}/summary

Get prediction summary and performance stats for a match.

**Response (200):**
```json
{
  "match_id": "match_abc123",
  "user_id": "usr_abc123",
  "total_predictions": 23,
  "correct_predictions": 14,
  "accuracy": 60.87,
  "total_points": 450,
  "current_streak": 3,
  "best_streak": 5,
  "confidence_boosts_used": 2,
  "confidence_boosts_remaining": 1,
  "predictions": [ ...prediction objects... ]
}
```

---

### GET /api/v1/predictions/history

Get paginated prediction history across all matches.

**Query params:**
| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `page` | int | 1 | Page number (>= 1) |
| `limit` | int | 20 | Results per page (1-100) |

**Response (200):**
```json
{
  "predictions": [ ...prediction objects... ],
  "total": 250,
  "page": 1,
  "limit": 20
}
```

---

### GET /api/v1/predictions/stats

Get lifetime prediction statistics breakdown.

**Response (200):**
```json
{
  "total_predictions": 250,
  "correct_predictions": 155,
  "accuracy": 62.0,
  "total_points": 5240,
  "best_streak": 12,
  "matches_played": 15,
  "by_type": {
    "ball": {
      "total": 200,
      "correct": 130,
      "accuracy": 65.0,
      "points": 3800
    },
    "over": {
      "total": 30,
      "correct": 15,
      "accuracy": 50.0,
      "points": 975
    },
    "milestone": {
      "total": 10,
      "correct": 7,
      "accuracy": 70.0,
      "points": 350
    },
    "match_winner": {
      "total": 10,
      "correct": 3,
      "accuracy": 30.0,
      "points": 115
    }
  }
}
```

---

## 5. Leaderboards

All leaderboard endpoints are public, but passing a Bearer token adds `my_rank` and `my_entry` to the response.

### Common Leaderboard Response Shape

```json
{
  "type": "match",
  "key": "match_abc123",
  "entries": [
    {
      "rank": 1,
      "user_id": "usr_abc123",
      "username": "john_doe",
      "display_name": "John Doe",
      "avatar_url": "https://...",
      "total_points": 450,
      "correct_predictions": 14,
      "accuracy": 60.9
    },
    {
      "rank": 2,
      "user_id": "usr_def456",
      "username": "jane_smith",
      "display_name": "Jane Smith",
      "avatar_url": null,
      "total_points": 380,
      "correct_predictions": 12,
      "accuracy": 55.0
    }
  ],
  "total_participants": 2450,
  "my_rank": 42,
  "my_entry": {
    "rank": 42,
    "user_id": "usr_me",
    "username": "my_username",
    "display_name": "My Name",
    "avatar_url": null,
    "total_points": 180,
    "correct_predictions": 8,
    "accuracy": 45.0
  },
  "page": 1,
  "limit": 50
}
```

**Note:** `my_rank` and `my_entry` are only present when authenticated.

### Leaderboard Endpoints

| Endpoint | Type | Key |
|----------|------|-----|
| `GET /leaderboards/match/{match_id}` | Per-match | match_id |
| `GET /leaderboards/daily` | Daily | YYYY-MM-DD |
| `GET /leaderboards/season` | Season | 2026 |
| `GET /leaderboards/competition/{competition_id}` | Competition | competition_id |
| `GET /leaderboards/league/{league_id}` | League | league_id |
| `GET /leaderboards/league/{league_id}/match/{match_id}` | League+Match | composite |

**Common query params for all:**
| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `limit` | int | 50 | Results per page (1-200) |
| `offset` | int | 0 | Pagination offset |

**Daily leaderboard extra param:**
| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `date` | string | today | Date in `YYYY-MM-DD` format |

---

## 6. Leagues

### POST /api/v1/leagues

Create a new league. Creator becomes owner and first member.

**Request:**
```json
{
  "name": "Office Cricket Club",
  "competition_id": "comp_ipl_2026"
}
```

| Field | Type | Required | Validation |
|-------|------|----------|------------|
| `name` | string | yes | 3-50 characters |
| `competition_id` | string | no | If set, league is scoped to that competition's matches only |

**Response (200):**
```json
{
  "league": {
    "id": "league_abc123",
    "name": "Office Cricket Club",
    "invite_code": "ABC12XYZ",
    "owner_id": "usr_abc123",
    "competition_id": "comp_ipl_2026",
    "members": [
      {
        "user_id": "usr_abc123",
        "joined_at": "2026-02-21T10:00:00Z"
      }
    ],
    "member_count": 1,
    "max_members": 50,
    "created_at": "2026-02-21T10:00:00Z",
    "updated_at": "2026-02-21T10:00:00Z"
  }
}
```

---

### GET /api/v1/leagues

Get all leagues the authenticated user is a member of.

**Response (200):**
```json
{
  "leagues": [ ...league objects... ],
  "total": 3
}
```

---

### GET /api/v1/leagues/{league_id}

Get league details with member list. Public endpoint.

**Response (200):**
```json
{
  "league": {
    "id": "league_abc123",
    "name": "Office Cricket Club",
    "invite_code": "ABC12XYZ",
    "owner_id": "usr_abc123",
    "competition_id": "comp_ipl_2026",
    "members": [
      {
        "user_id": "usr_abc123",
        "username": "john_doe",
        "display_name": "John Doe",
        "avatar_url": "https://...",
        "total_points": 450,
        "rank": 1,
        "joined_at": "2026-02-21T10:00:00Z"
      }
    ],
    "member_count": 3,
    "max_members": 50,
    "created_at": "2026-02-21T10:00:00Z",
    "updated_at": "2026-02-21T10:00:00Z"
  }
}
```

---

### POST /api/v1/leagues/join

Join a league using invite code.

**Request:**
```json
{
  "invite_code": "ABC12XYZ"
}
```

**Response (200):**
```json
{
  "league": { ...league object... },
  "message": "Joined successfully"
}
```

**Errors:**
- 404: Invalid invite code
- 400: League is full (50 members max)
- 400: Already a member

---

### DELETE /api/v1/leagues/{league_id}/leave

Leave a league. Owner cannot leave.

**Response (200):**
```json
{
  "message": "Left league successfully"
}
```

---

## 7. Competitions

Competitions are platform-seeded tournaments (IPL, T20 World Cup). Public endpoints.

### GET /api/v1/competitions

List all competitions.

**Query params:**
| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `is_active` | bool | — | Filter by active status |
| `season` | string | — | Filter by season (e.g., "2026") |

**Response (200):**
```json
{
  "competitions": [
    {
      "id": "comp_ipl_2026",
      "name": "Indian Premier League 2026",
      "short_name": "IPL",
      "match_type": "T20",
      "season": "2026",
      "start_date": "2026-03-26T00:00:00Z",
      "end_date": "2026-05-25T23:59:59Z",
      "is_active": true,
      "is_platform_seeded": true,
      "teams": [
        "Chennai Super Kings", "Mumbai Indians", "Royal Challengers Bengaluru",
        "Kolkata Knight Riders", "Delhi Capitals", "Punjab Kings",
        "Rajasthan Royals", "Sunrisers Hyderabad", "Gujarat Titans", "Lucknow Super Giants"
      ],
      "match_count": 74,
      "created_at": "2026-02-15T10:00:00Z",
      "updated_at": "2026-02-15T10:00:00Z"
    },
    {
      "id": "comp_t20wc_2026",
      "name": "ICC Men's T20 World Cup 2026",
      "short_name": "T20WC",
      "match_type": "T20",
      "season": "2026",
      "start_date": "2026-02-09T00:00:00Z",
      "end_date": "2026-03-07T23:59:59Z",
      "is_active": true,
      "is_platform_seeded": true,
      "teams": [
        "India", "Australia", "England", "South Africa", "New Zealand",
        "Pakistan", "West Indies", "Sri Lanka", "Bangladesh", "Afghanistan",
        "Zimbabwe", "Ireland", "Scotland", "Netherlands", "Namibia", "United States"
      ],
      "match_count": 0,
      "created_at": "2026-02-15T10:00:00Z",
      "updated_at": "2026-02-15T10:00:00Z"
    }
  ],
  "total": 2
}
```

---

### GET /api/v1/competitions/{competition_id}

Get single competition details.

---

### GET /api/v1/competitions/{competition_id}/matches

Get all matches in a competition.

**Response (200):**
```json
{
  "competition": { ...competition object... },
  "matches": [ ...match objects... ],
  "total": 74
}
```

---

### POST /api/v1/competitions (Admin only)

Create a new competition.

**Request:**
```json
{
  "name": "Indian Premier League 2026",
  "short_name": "IPL",
  "match_type": "T20",
  "season": "2026",
  "start_date": "2026-03-26T00:00:00Z",
  "end_date": "2026-05-25T23:59:59Z",
  "teams": ["Chennai Super Kings", "Mumbai Indians"]
}
```

---

## 8. AI & ML Features

### GET /api/v1/ai/match/{match_id}/probabilities

Get ML-predicted probabilities for the next ball outcome.

**Response (200):**
```json
{
  "match_id": "match_abc123",
  "ball_key": "1.16.1",
  "probabilities": {
    "dot": 0.32,
    "1": 0.28,
    "2": 0.12,
    "3": 0.03,
    "4": 0.13,
    "6": 0.07,
    "wicket": 0.05
  },
  "model_version": "v2"
}
```

**UI Tip:** Display these as a horizontal bar chart or radial chart to help users make informed predictions.

---

### GET /api/v1/ai/match/{match_id}/commentary

Get AI-generated commentary (ball-by-ball and over summaries).

**Query params:**
| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `limit` | int | 10 | Number of recent entries |

**Response (200):**
```json
{
  "match_id": "match_abc123",
  "commentary": [
    {
      "_id": "content_abc123",
      "match_id": "match_abc123",
      "type": "ball_commentary",
      "content": "Rohit Sharma leans back and cuts hard through point — the fielder dives but it races away to the boundary! Four runs!",
      "model_used": "claude-haiku-4-5-20251001",
      "tokens_used": 85,
      "generation_time_ms": 320,
      "created_at": "2026-03-26T20:15:30Z"
    },
    {
      "_id": "content_def456",
      "match_id": "match_abc123",
      "type": "over_summary",
      "content": "Over 16: MI 145/3 (RR: 9.06). Rohit Sharma dominated this over with two boundaries...",
      "model_used": "claude-haiku-4-5-20251001",
      "tokens_used": 120,
      "generation_time_ms": 450,
      "created_at": "2026-03-26T20:16:00Z"
    }
  ]
}
```

**AI Content Types:**
| Type | Model | Description |
|------|-------|-------------|
| `pre_match_brief` | Claude Sonnet 4 | 300-500 word pre-match preview |
| `post_match_report` | Claude Sonnet 4 | 500-800 word post-match analysis |
| `ball_commentary` | Claude Haiku 4.5 | Real-time ball-by-ball commentary (50-100 words) |
| `over_summary` | Claude Haiku 4.5 | End-of-over summary (50-100 words) |

---

### GET /api/v1/matches/{match_id}/ai-preview

Get pre-match AI preview.

**Response (200):**
```json
{
  "match_id": "match_abc123",
  "content": "The stage is set for an electrifying IPL 2026 opener as Chennai Super Kings host Mumbai Indians at the iconic MA Chidambaram Stadium...",
  "generated_at": "2026-03-26T18:00:00Z"
}
```

---

### GET /api/v1/matches/{match_id}/ai-report

Get post-match AI report.

**Response (200):**
```json
{
  "match_id": "match_abc123",
  "content": "In a match that will be talked about for years, Chennai Super Kings pulled off a dramatic 4-wicket victory...",
  "generated_at": "2026-03-26T23:00:00Z"
}
```

---

## 9. Social Features

### POST /api/v1/social/share-card/{match_id}

Generate a share card image for a match. Returns S3 URL.

**Response (200):**
```json
{
  "share_id": "share_abc123",
  "image_url": "https://calledit-assets.s3.ap-south-1.amazonaws.com/share-cards/abc123.png"
}
```

**Image specs:**
- Dimensions: 1200 x 630 px (social media optimized)
- Contains: Match info, user's prediction stats, accuracy, best streak
- Dark navy background with indigo accents

---

### GET /api/v1/social/share/{share_id}

Get share card details (for deep links / OG tags).

**Response (200):**
```json
{
  "_id": "share_abc123",
  "user_id": "usr_abc123",
  "match_id": "match_abc123",
  "image_url": "https://...",
  "created_at": "2026-03-26T22:30:00Z"
}
```

---

### POST /api/v1/social/referral/verify

Apply a referral code. Awards "Recruiter" badge to referrer.

**Query params:**
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `referral_code` | string | yes | Friend's referral code |

**Response (200):**
```json
{
  "message": "Referral applied successfully",
  "referrer": "john_doe"
}
```

---

## 10. Admin Endpoints

All admin endpoints require `Authorization: Bearer <token>` where the user has `is_admin: true`.

### POST /api/v1/admin/matches/sync

Sync matches from CricAPI into database.

**Query params:**
| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `match_type` | string | `"T20"` | Filter: `"T20"`, `"ODI"`, `"Test"`, `"all"` |

**Response (200):**
```json
{
  "synced": 3,
  "match_ids": ["match_001", "match_002", "match_003"]
}
```

---

### POST /api/v1/admin/matches/{match_id}/status

Manually update match status.

**Query params:**
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `new_status` | string | yes | One of the MatchStatus values |

---

### POST /api/v1/admin/ai/generate-preview/{match_id}

Trigger AI pre-match preview generation.

**Response (200):**
```json
{
  "message": "AI preview generated",
  "content_id": "content_abc123"
}
```

---

### GET /api/v1/admin/stats/dashboard

Platform-wide statistics.

**Response (200):**
```json
{
  "total_users": 5234,
  "total_predictions": 245000,
  "total_matches": 145,
  "live_matches": 2,
  "total_leagues": 342,
  "new_users_24h": 124,
  "predictions_24h": 8450
}
```

---

## 11. WebSocket (Real-Time)

Uses **Socket.IO** (not raw WebSocket). Connect with a Socket.IO client library.

### Connection

```javascript
import { io } from "socket.io-client";

const socket = io("http://localhost:8000", {
  auth: {
    token: "your_access_token_jwt"
  },
  transports: ["websocket", "polling"]
});

socket.on("connect", () => {
  console.log("Connected:", socket.id);
});

socket.on("connect_error", (err) => {
  console.error("Connection failed:", err.message);
});
```

**Note:** The Socket.IO server runs on the same port as the HTTP API.

---

### Client → Server Events

#### join_match
```javascript
socket.emit("join_match", { match_id: "match_abc123" });
```
Joins room `match:{match_id}`. Server responds with `match_state` event.

#### leave_match
```javascript
socket.emit("leave_match", { match_id: "match_abc123" });
```
Leaves room `match:{match_id}`. Stops receiving updates for that match.

---

### Server → Client Events

#### match_state
Received immediately after `join_match`. Contains full current match state.

```javascript
socket.on("match_state", (data) => {
  // data = full match object (same shape as GET /matches/{id} response)
});
```

#### ball_update
Fired after each ball is bowled.

```javascript
socket.on("ball_update", (data) => {
  // data = {
  //   match_id: "match_abc123",
  //   ball_key: "1.16.2",
  //   innings: 1,
  //   over: 16,
  //   ball: 2,
  //   batter: "Rohit Sharma",
  //   bowler: "Deepak Chahar",
  //   outcome: "4",
  //   batter_runs: 4,
  //   extras: 0,
  //   total_runs: 4,
  //   is_wicket: false,
  //   score: 149,
  //   wickets: 3,
  //   overs: 16.2,
  //   run_rate: 9.15
  // }
});
```

#### prediction_window
Fired when prediction window opens/closes (15 seconds before each ball).

```javascript
socket.on("prediction_window", (data) => {
  // data = {
  //   match_id: "match_abc123",
  //   is_open: true,
  //   ball_key: "1.16.3",
  //   innings: 1,
  //   over: 16,
  //   ball: 3,
  //   closes_at: "2026-03-26T20:16:30Z"
  // }
});
```

**UI behavior:**
- When `is_open: true` → Show prediction UI with countdown timer (15 seconds)
- When `is_open: false` → Hide/disable prediction UI, show "waiting for next ball"

#### score_update
Fired when score changes (can follow ball_update).

```javascript
socket.on("score_update", (data) => {
  // data = {
  //   match_id: "match_abc123",
  //   innings: 1,
  //   score: 149,
  //   wickets: 3,
  //   overs: 16.2,
  //   run_rate: 9.15,
  //   batting_team: "Mumbai Indians"
  // }
});
```

#### leaderboard_update
Fired after predictions are resolved (after each ball).

```javascript
socket.on("leaderboard_update", (data) => {
  // data = {
  //   match_id: "match_abc123",
  //   entries: [
  //     { rank: 1, user_id: "...", username: "...", total_points: 450 },
  //     { rank: 2, user_id: "...", username: "...", total_points: 380 },
  //     ...top 10
  //   ]
  // }
});
```

#### notification
User-specific notification (prediction result, badge, streak).

```javascript
socket.on("notification", (data) => {
  // data = {
  //   type: "prediction_result",
  //   title: "Correct!",
  //   body: "Your ball prediction was correct! +30 points",
  //   data: {
  //     match_id: "match_abc123",
  //     prediction_id: "pred_xyz789",
  //     is_correct: true,
  //     points: 30
  //   }
  // }
});
```

**Notification types:**
| Type | When | Data fields |
|------|------|-------------|
| `prediction_result` | Prediction resolved | `match_id`, `prediction_id`, `is_correct`, `points` |
| `streak` | Streak milestone hit | `match_id`, `streak_count` |
| `badge` | New badge earned | `badge_id`, `badge_name` |
| `league` | League member activity | `league_id`, `action` |
| `match_start` | Match goes live | `match_id` |
| `match_end` | Match completed | `match_id`, `winner` |
| `leaderboard` | Rank change | `match_id`, `new_rank` |

#### match_status
Fired when match status changes (upcoming → live_1st → innings_break → live_2nd → completed).

```javascript
socket.on("match_status", (data) => {
  // data = {
  //   match_id: "match_abc123",
  //   status: "live_1st",
  //   previous_status: "toss"
  // }
});
```

#### ai_commentary
Real-time AI ball commentary.

```javascript
socket.on("ai_commentary", (data) => {
  // data = {
  //   match_id: "match_abc123",
  //   ball_key: "1.16.2",
  //   commentary: "Rohit Sharma leans back and smashes it through covers..."
  // }
});
```

#### over_summary
AI-generated over summary at end of each over.

```javascript
socket.on("over_summary", (data) => {
  // data = {
  //   match_id: "match_abc123",
  //   innings: 1,
  //   over: 16,
  //   summary: "Over 16: MI 149/3 (RR: 9.15). Two boundaries from Rohit..."
  // }
});
```

---

## 12. Scoring System

### Points Table

| Prediction Type | Outcome | Base Points |
|-----------------|---------|-------------|
| Ball (correct) | Exact match | 10 |
| Over (exact) | Exact runs | 25 |
| Over (close) | Within ±3 runs | 10 |
| Milestone | Correct | 50 |
| Match Winner | Correct | 100 |

### Multipliers

All multipliers stack multiplicatively.

#### Streak Multiplier
Consecutive correct ball predictions:

| Streak Length | Multiplier |
|---------------|------------|
| 0-2 correct | 1.0x |
| 3-4 correct | 1.5x |
| 5-9 correct | 2.0x |
| 10+ correct | 3.0x |

Streak resets on incorrect prediction. Only applies to ball predictions.

#### Confidence Boost (2.0x)
- Player can activate on up to **3 balls per match**
- If correct: points doubled (2.0x multiplier)
- If wrong: no penalty (just wasted boost)
- Show remaining boosts in UI: `confidence_boosts_remaining` from match summary

#### Clutch Multiplier (2.0x)
- Automatically applied for correct ball predictions in **overs 15-20** (death overs)
- Stacks with other multipliers

### Points Formula

```
total_points = base_points × streak_multiplier × confidence_multiplier × clutch_multiplier
```

**Example:** Correct ball prediction in over 18 with 5-streak and confidence boost:
```
10 × 2.0 (streak) × 2.0 (confidence) × 2.0 (clutch) = 80 points
```

---

## 13. Badges

Badges are awarded automatically. Display them on user profiles and in notifications.

| Badge ID | Display Name | Icon | How to Earn |
|----------|-------------|------|-------------|
| `first_prediction` | First Call | trophy | Make your first prediction |
| `streak_5` | On Fire | fire | Get 5 correct predictions in a row |
| `streak_10` | Unstoppable | lightning | Get 10 correct predictions in a row |
| `century` | Century Maker | 100 | Earn 100+ points in a single match |
| `clutch_master` | Clutch Master | target | Get 5+ correct clutch predictions (overs 15-20) |
| `match_winner_3` | Oracle | crystal_ball | Correctly predict 3 match winners |
| `league_creator` | League Founder | crown | Create a league |
| `social_sharer` | Show Off | share | Share a match card |
| `referral_1` | Recruiter | handshake | Have someone use your referral code |
| `matches_10` | Regular | calendar | Play in 10 matches |
| `matches_50` | Veteran | medal | Play in 50 matches |
| `top_10` | Elite | star | Finish in top 10 of a match leaderboard |

**User's badges** are returned as an array of badge IDs in the user profile (`badges: ["first_prediction", "streak_5"]`).

---

## 14. Constants & Enums

### Match Status Flow

```
upcoming → toss → live_1st → innings_break → live_2nd → completed
                                                        → abandoned
```

### Ball Outcomes (7 classes)
```
"dot" | "1" | "2" | "3" | "4" | "6" | "wicket"
```

### Prediction Types
```
"ball" | "over" | "milestone" | "match_winner"
```

### Milestone Types
```
"batter_50" | "batter_100" | "bowler_3w" | "bowler_5w" | "team_200"
```

### Match Phases (for UI context)
| Phase | Overs | Style |
|-------|-------|-------|
| Powerplay | 1-6 | Aggressive batting, field restrictions |
| Middle | 7-14 | Building innings, rotating strike |
| Death | 15-20 | All-out attack, clutch multiplier active |

### IPL Teams
| Code | Full Name |
|------|-----------|
| CSK | Chennai Super Kings |
| MI | Mumbai Indians |
| RCB | Royal Challengers Bengaluru |
| KKR | Kolkata Knight Riders |
| DC | Delhi Capitals |
| PBKS | Punjab Kings |
| RR | Rajasthan Royals |
| SRH | Sunrisers Hyderabad |
| GT | Gujarat Titans |
| LSG | Lucknow Super Giants |

---

## 15. Error Handling

### HTTP Status Codes

| Code | Meaning |
|------|---------|
| 200 | Success |
| 400 | Bad request (validation error, business logic error) |
| 401 | Unauthorized (missing/invalid/expired token) |
| 403 | Forbidden (not admin) |
| 404 | Not found |
| 409 | Conflict (duplicate username, already joined league) |
| 429 | Rate limited |
| 500 | Server error |

### Error Response Shape

```json
{
  "detail": "Match is not live"
}
```

Or for validation errors (422):
```json
{
  "detail": [
    {
      "loc": ["body", "prediction"],
      "msg": "value is not a valid enumeration member",
      "type": "value_error.enum",
      "ctx": {"enum_values": ["dot", "1", "2", "3", "4", "6", "wicket"]}
    }
  ]
}
```

### Token Refresh Flow

```
1. API returns 401 Unauthorized
2. Call POST /auth/refresh with refresh_token
3. If 200 → store new tokens, retry original request
4. If 401 → refresh token expired → redirect to login
```

---

## 16. Complete User Flow

### First-Time User

```
1. Launch app → Login screen
2. Enter phone → POST /auth/otp/send
3. Enter OTP → POST /auth/otp/verify → get tokens, is_new_user: true
4. Onboarding screen:
   - Set username + display name
   - Pick favourite team (show IPL_TEAMS)
   - Pick favourite players
   - Enter referral code (optional)
   → POST /users/me/onboarding
5. Home screen → GET /matches (upcoming + live)
6. If competitions available → GET /competitions
```

### Match Day (Live Match)

```
1. Home screen shows live matches → GET /matches/live
2. Tap match → GET /matches/{id} for details
3. See AI preview → GET /matches/{id}/ai-preview
4. Connect WebSocket: socket.emit("join_match", {match_id})
5. Receive match_state → render scorecard
6. Predict match winner → POST /predictions/match-winner

LIVE LOOP (repeats every ball):
├── Receive prediction_window {is_open: true}
│   └── Show prediction UI with 15-second countdown
│       ├── Show ML probabilities → GET /ai/match/{id}/probabilities
│       ├── User picks outcome → POST /predictions/ball
│       └── Optional: confidence boost toggle
├── Receive ball_update → update scorecard
├── Receive score_update → update score display
├── Receive notification {type: "prediction_result"}
│   └── Show result toast: "Correct! +30 pts" or "Wrong! It was a 4"
├── Receive leaderboard_update → update mini leaderboard
├── Receive ai_commentary → show commentary text
├── End of over:
│   ├── User can predict over runs → POST /predictions/over
│   ├── Receive over_summary → show over summary card
│   └── User can predict milestones → POST /predictions/milestone
└── Repeat

7. Innings break:
   ├── Receive match_status {status: "innings_break"}
   ├── Allow match_winner prediction update
   └── Show innings 1 summary

8. Second innings (same loop, innings: 2)

9. Match ends:
   ├── Receive match_status {status: "completed"}
   ├── Show final scorecard
   ├── GET /predictions/match/{id}/summary → show performance
   ├── GET /leaderboards/match/{id} → show final standings
   ├── GET /matches/{id}/ai-report → show post-match AI analysis
   └── POST /social/share-card/{id} → generate share image
```

### Leaderboard Screens

```
- Match leaderboard: GET /leaderboards/match/{id}
- Daily leaderboard: GET /leaderboards/daily
- Season leaderboard: GET /leaderboards/season
- Competition leaderboard: GET /leaderboards/competition/{id}
- League leaderboard: GET /leaderboards/league/{id}
- League+Match leaderboard: GET /leaderboards/league/{lid}/match/{mid}

All return same shape. Show "my_rank" badge when authenticated.
```

### League Flow

```
1. Create league: POST /leagues → get invite_code
2. Share invite_code with friends (in-app share or clipboard)
3. Friend joins: POST /leagues/join {invite_code}
4. View league: GET /leagues/{id} → see members + leaderboard
5. League leaderboard: GET /leaderboards/league/{id}
```

### Profile & Stats

```
- My profile: GET /users/me
- Edit profile: PATCH /users/me
- Prediction history: GET /predictions/history?page=1&limit=20
- Overall stats: GET /predictions/stats
- Other user's profile: GET /users/{id}
- Other user's predictions: GET /users/{id}/predictions
```

---

## Appendix A: CORS & Deployment

### Local Development
```
Backend: http://localhost:8000
Frontend: http://localhost:3000
```

### Production (EC2)
```
Backend: https://api.calledit.in (behind nginx/ALB)
Frontend: https://calledit.in
```

The backend CORS is configured via `ALLOWED_ORIGINS` env var (comma-separated):
```
ALLOWED_ORIGINS=https://calledit.in,https://www.calledit.in
```

### Required Infrastructure
| Service | Purpose |
|---------|---------|
| MongoDB | Primary database |
| Redis | Caching, leaderboards (ZSET), OTP storage, streaks |
| S3 | Share card image uploads |
| Twilio | OTP SMS delivery |
| Claude API | AI content generation |
| CricAPI v2 | Live cricket data |

---

## Appendix B: Recommended Libraries

### React Native / React
| Purpose | Library |
|---------|---------|
| HTTP client | `axios` or `fetch` with interceptors for token refresh |
| WebSocket | `socket.io-client` (v4+) |
| State | `zustand` or `@tanstack/react-query` for server state |
| Storage | `@react-native-async-storage/async-storage` (RN) or `localStorage` (web) |

### Socket.IO Client Setup

```javascript
import { io } from "socket.io-client";

const API_URL = "http://localhost:8000"; // or production URL

// Create socket with auth
const createSocket = (accessToken) => {
  return io(API_URL, {
    auth: { token: accessToken },
    transports: ["websocket", "polling"],
    reconnection: true,
    reconnectionAttempts: 10,
    reconnectionDelay: 1000,
  });
};

// Usage
const socket = createSocket(myAccessToken);

// Join a match room
socket.emit("join_match", { match_id: "match_abc123" });

// Listen for events
socket.on("ball_update", handleBallUpdate);
socket.on("prediction_window", handlePredictionWindow);
socket.on("score_update", handleScoreUpdate);
socket.on("notification", handleNotification);
socket.on("leaderboard_update", handleLeaderboardUpdate);
socket.on("ai_commentary", handleCommentary);
socket.on("over_summary", handleOverSummary);
socket.on("match_status", handleMatchStatus);

// Leave match room
socket.emit("leave_match", { match_id: "match_abc123" });

// Disconnect
socket.disconnect();
```

### Axios Interceptor for Token Refresh

```javascript
import axios from "axios";

const api = axios.create({
  baseURL: "http://localhost:8000/api/v1",
});

// Request interceptor — attach token
api.interceptors.request.use((config) => {
  const token = getAccessToken(); // from your storage
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Response interceptor — refresh on 401
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;
    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true;
      try {
        const refreshToken = getRefreshToken();
        const { data } = await axios.post(
          "http://localhost:8000/api/v1/auth/refresh",
          { refresh_token: refreshToken }
        );
        setAccessToken(data.access_token);
        setRefreshToken(data.refresh_token);
        originalRequest.headers.Authorization = `Bearer ${data.access_token}`;
        return api(originalRequest);
      } catch (refreshError) {
        // Refresh failed — redirect to login
        logout();
        return Promise.reject(refreshError);
      }
    }
    return Promise.reject(error);
  }
);

export default api;
```

---

## Appendix C: Key UI Components to Build

| Component | Data Source | Key Features |
|-----------|-----------|--------------|
| **Login Screen** | `/auth/otp/send`, `/auth/otp/verify` | Phone input, OTP input, timer |
| **Onboarding** | `/users/me/onboarding` | Username, team picker, referral |
| **Match List** | `/matches` | Tabs: Upcoming/Live/Completed, pull-to-refresh |
| **Live Match** | WebSocket + `/matches/{id}` | Real-time scorecard, ball-by-ball |
| **Prediction Panel** | `/predictions/ball` | 7 outcome buttons, confidence boost toggle, countdown timer |
| **Over Prediction** | `/predictions/over` | Runs slider/input (0-50) |
| **Match Winner** | `/predictions/match-winner` | Team selector, change counter |
| **Milestone** | `/predictions/milestone` | Type picker, player name, yes/no |
| **ML Probabilities** | `/ai/match/{id}/probabilities` | Bar chart / pie chart of 7 outcomes |
| **Win Probability** | `/matches/{id}/win-probability` | Animated line chart over time |
| **AI Commentary** | WebSocket `ai_commentary` | Scrolling text feed |
| **Leaderboard** | `/leaderboards/*` | Ranked list, "my rank" highlight |
| **League** | `/leagues/*` | Create, join, invite code share |
| **Competition** | `/competitions/*` | Tournament bracket / match list |
| **Profile** | `/users/me` | Stats cards, badge grid, prediction history |
| **Share Card** | `/social/share-card/{id}` | Share image preview, share buttons |
| **Badge Display** | User profile `badges` array | Grid of earned badges with icons |
| **Notification Toast** | WebSocket `notification` | In-app toast/snackbar |
| **Admin Dashboard** | `/admin/stats/dashboard` | Stats cards, sync button |
