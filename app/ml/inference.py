"""ML inference wrapper for CalledIt ML models.

Supports both ONNX Runtime and native XGBoost model formats.
Prefers ONNX if available, falls back to native XGBoost JSON.
"""

import json
import logging
from pathlib import Path
import numpy as np

logger = logging.getLogger(__name__)

MODEL_DIR = Path(__file__).parent / "models"
BALL_ONNX_PATH = MODEL_DIR / "ball_outcome_model.onnx"
BALL_NATIVE_PATH = MODEL_DIR / "ball_outcome_model.json"
WIN_ONNX_PATH = MODEL_DIR / "win_probability_model.onnx"
WIN_NATIVE_PATH = MODEL_DIR / "win_probability_model.json"
TEAM_ENCODER_PATH = MODEL_DIR / "team_encoder.json"

OUTCOME_NAMES = {0: "dot", 1: "1", 2: "2", 3: "3", 4: "4", 5: "6", 6: "wicket"}

# Uniform fallback when model not loaded
UNIFORM_BALL_PROBS = {name: round(1 / 7, 4) for name in OUTCOME_NAMES.values()}


class MLInference:
    """Loads ML models and runs inference for ball outcomes and win probability."""

    def __init__(self):
        self._ball_session = None  # ONNX session
        self._win_session = None   # ONNX session
        self._ball_model = None    # Native XGBoost model
        self._win_model = None     # Native XGBoost model
        self._team_encoder: dict[str, int] = {}
        self._loaded = False

    def load_models(self) -> None:
        """Load models from disk. Tries ONNX first, falls back to native XGBoost."""
        # Try ONNX first
        ort_available = False
        try:
            import onnxruntime as ort
            ort_available = True
        except ImportError:
            logger.info("onnxruntime not available, will use native XGBoost")

        # Ball outcome model
        if ort_available and BALL_ONNX_PATH.exists():
            try:
                self._ball_session = ort.InferenceSession(
                    str(BALL_ONNX_PATH), providers=["CPUExecutionProvider"],
                )
                logger.info(f"Ball model loaded (ONNX): {BALL_ONNX_PATH}")
            except Exception as e:
                logger.warning(f"ONNX ball model load failed: {e}")
        if self._ball_session is None and BALL_NATIVE_PATH.exists():
            try:
                import xgboost as xgb
                self._ball_model = xgb.XGBClassifier()
                self._ball_model.load_model(str(BALL_NATIVE_PATH))
                logger.info(f"Ball model loaded (native): {BALL_NATIVE_PATH}")
            except Exception as e:
                logger.warning(f"Native ball model load failed: {e}")

        # Win probability model
        if ort_available and WIN_ONNX_PATH.exists():
            try:
                self._win_session = ort.InferenceSession(
                    str(WIN_ONNX_PATH), providers=["CPUExecutionProvider"],
                )
                logger.info(f"Win model loaded (ONNX): {WIN_ONNX_PATH}")
            except Exception as e:
                logger.warning(f"ONNX win model load failed: {e}")
        if self._win_session is None and WIN_NATIVE_PATH.exists():
            try:
                import xgboost as xgb
                self._win_model = xgb.XGBClassifier()
                self._win_model.load_model(str(WIN_NATIVE_PATH))
                logger.info(f"Win model loaded (native): {WIN_NATIVE_PATH}")
            except Exception as e:
                logger.warning(f"Native win model load failed: {e}")

        # Team encoder
        if TEAM_ENCODER_PATH.exists():
            try:
                with open(TEAM_ENCODER_PATH) as f:
                    self._team_encoder = json.load(f)
                logger.info(f"Team encoder loaded: {len(self._team_encoder)} teams")
            except Exception as e:
                logger.warning(f"Team encoder load failed: {e}")

        has_ball = self._ball_session is not None or self._ball_model is not None
        has_win = self._win_session is not None or self._win_model is not None

        if not has_ball and not has_win:
            logger.warning("No ML models loaded — using uniform/50-50 fallback")
        self._loaded = True

    def get_team_id(self, team_name: str) -> int:
        """Get encoded team ID. Returns 0 for unknown teams."""
        return self._team_encoder.get(team_name, 0)

    def predict_ball_outcome(self, features: np.ndarray) -> dict[str, float]:
        """Predict ball outcome probabilities. Returns dict mapping outcome names to probabilities."""
        # ONNX inference
        if self._ball_session is not None:
            try:
                input_name = self._ball_session.get_inputs()[0].name
                outputs = self._ball_session.run(None, {input_name: features.astype(np.float32)})
                probabilities = outputs[1][0]
                if isinstance(probabilities, dict):
                    return {OUTCOME_NAMES[i]: float(probabilities.get(i, 0)) for i in range(7)}
                return {OUTCOME_NAMES[i]: float(probabilities[i]) for i in range(7)}
            except Exception as e:
                logger.error(f"ONNX ball prediction failed: {e}")

        # Native XGBoost inference
        if self._ball_model is not None:
            try:
                probs = self._ball_model.predict_proba(features.astype(np.float32))
                return {OUTCOME_NAMES[i]: float(probs[0][i]) for i in range(7)}
            except Exception as e:
                logger.error(f"Native ball prediction failed: {e}")

        return UNIFORM_BALL_PROBS.copy()

    def predict_win_probability(
        self, features: np.ndarray, teams: tuple[str, str]
    ) -> dict[str, float]:
        """Predict win probability for each team."""
        # ONNX inference
        if self._win_session is not None:
            try:
                input_name = self._win_session.get_inputs()[0].name
                outputs = self._win_session.run(None, {input_name: features.astype(np.float32)})
                probabilities = outputs[1][0]
                if isinstance(probabilities, dict):
                    batting_win_prob = float(probabilities.get(1, 0.5))
                else:
                    batting_win_prob = float(probabilities[1]) if len(probabilities) > 1 else 0.5
                return {teams[0]: round(batting_win_prob, 4), teams[1]: round(1 - batting_win_prob, 4)}
            except Exception as e:
                logger.error(f"ONNX win prediction failed: {e}")

        # Native XGBoost inference
        if self._win_model is not None:
            try:
                probs = self._win_model.predict_proba(features.astype(np.float32))
                batting_win_prob = float(probs[0][1])
                return {teams[0]: round(batting_win_prob, 4), teams[1]: round(1 - batting_win_prob, 4)}
            except Exception as e:
                logger.error(f"Native win prediction failed: {e}")

        return {teams[0]: 0.5, teams[1]: 0.5}

    @property
    def is_loaded(self) -> bool:
        return self._loaded
