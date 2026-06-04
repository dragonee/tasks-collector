from django.test import TestCase

from tasks.apps.rewards.models import Claim, Reward

from .models import Challenge, ChallengeStage, ChallengeStageCompleted, Element
from .services.evaluation import evaluate_challenge


class EvaluateChallengeTests(TestCase):
    def setUp(self):
        self.r1 = Reward.objects.create(name="R1", slug="r1")
        self.r2 = Reward.objects.create(name="R2", slug="r2")

        self.challenge = Challenge.objects.create(name="Balance", slug="balance")
        self.s1 = ChallengeStage.objects.create(
            challenge=self.challenge, order=1, si=1, reward=self.r1
        )
        self.s2 = ChallengeStage.objects.create(
            challenge=self.challenge,
            order=2,
            ne=1,
            fi=1,
            te=1,
            si=1,
            reward=self.r2,
            is_completion=True,
        )

    def _log(self, function, n=1):
        for _ in range(n):
            Element.objects.create(function=function)

    def test_no_grant_below_threshold(self):
        self.assertEqual(evaluate_challenge(self.challenge), [])
        self.assertEqual(Claim.objects.count(), 0)

    def test_grant_first_stage(self):
        self._log(Element.Function.SI, 1)

        claims = evaluate_challenge(self.challenge)

        self.assertEqual(len(claims), 1)
        self.assertEqual(claims[0].reward, self.r1)
        self.assertEqual(
            ChallengeStageCompleted.objects.filter(stage=self.s1).count(), 1
        )

    def test_no_double_grant(self):
        self._log(Element.Function.SI, 1)
        evaluate_challenge(self.challenge)

        self.assertEqual(evaluate_challenge(self.challenge), [])
        self.assertEqual(
            ChallengeStageCompleted.objects.filter(stage=self.s1).count(), 1
        )

    def test_completion_grants_all_reached_and_deactivates(self):
        for fn in (
            Element.Function.NE,
            Element.Function.FI,
            Element.Function.TE,
            Element.Function.SI,
        ):
            self._log(fn, 1)

        claims = evaluate_challenge(self.challenge)

        # Crossing (1,1,1,1) satisfies both stage 1 (si>=1) and the completion stage.
        self.assertEqual(len(claims), 2)

        self.challenge.refresh_from_db()
        self.assertFalse(self.challenge.active)
        self.assertIsNotNone(self.challenge.completed_at)

    def test_inactive_challenge_is_skipped(self):
        self.challenge.active = False
        self.challenge.save()
        self._log(Element.Function.SI, 1)

        self.assertEqual(evaluate_challenge(self.challenge), [])
