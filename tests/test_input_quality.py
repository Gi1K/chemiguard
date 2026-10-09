import base64
import hashlib
import json
import unittest
from unittest.mock import MagicMock, patch

import cv2
import numpy as np
import torch

from chemiguard.decisions import observe
from chemiguard.observation import face_quality, select_candidate
from chemiguard.vision import Vision, head_region, observation_image


class InputQuality(unittest.TestCase):
    def test_small_partial_person_uses_original_pixels_without_inventing_body_regions(self):
        vision = Vision.__new__(Vision)
        vision.pose = MagicMock()
        person = np.zeros((44, 68, 3), dtype=np.uint8)
        body = vision.body(person)
        self.assertEqual(body['route'], 'partial_person_only')
        self.assertEqual(list(body['images']), ['person'])
        self.assertIs(body['images']['person'], person)
        self.assertEqual(body['keypoints'], [])
        vision.pose.predict.assert_not_called()
        self.assertIsNone(vision.body(person[:31]))

    def landmarks(self):
        points = np.zeros((17, 2), dtype=np.float32)
        confidence = np.zeros(17, dtype=np.float32)
        # Raised shoulder above the face: the old shoulder cutoff omitted the jaw.
        for index, point in {0: (190, 170), 3: (165, 155), 5: (100, 120),
                             6: (230, 220), 11: (130, 350), 12: (240, 350)}.items():
            points[index], confidence[index] = point, .9
        return points, confidence

    def test_profile_and_raised_arm_keep_jaw_margin(self):
        points, confidence = self.landmarks()
        box, info = head_region(points, confidence, 400, 650)
        self.assertLess(box[0], 165)
        self.assertGreater(box[2], 220)
        self.assertGreater(box[3], 250)
        self.assertEqual(info['method'], 'face_landmarks_with_jaw_margin')
        json.dumps(info)
        points[0], points[3] = (390, 170), (375, 155)
        box, info = head_region(points, confidence, 400, 650)
        self.assertEqual(box[2], 400)
        self.assertGreater(info['clipped_edges'], 0)

    def test_missing_face_is_context_not_visibility(self):
        points, confidence = self.landmarks()
        confidence[:5] = 0
        box, info = head_region(points, confidence, 400, 650)
        image = np.zeros((box[3]-box[1], box[2]-box[0], 3), dtype=np.uint8)
        quality = face_quality({'images': {'head': image}, 'head_region': info})
        self.assertEqual(quality['visibility_proxy'], 0)
        self.assertEqual(quality['score'], 0)
        self.assertEqual(info['method'], 'upper_body_context')

    def test_head_survives_weak_torso_but_not_ambiguous_person_association(self):
        points, confidence = self.landmarks()
        confidence[11:13] = 0
        result = MagicMock()
        result.boxes.xyxy = torch.tensor([[0, 0, 400, 650]])
        result.keypoints.__len__.return_value = 1
        result.keypoints.xy = torch.tensor(points[None])
        result.keypoints.conf = torch.tensor(confidence[None])
        vision = Vision.__new__(Vision)
        vision.pose = MagicMock()
        vision.pose.predict.return_value = [result]
        person = np.zeros((650, 400, 3), dtype=np.uint8)
        body = vision.body(person)
        self.assertEqual(body['route'], 'pose_head_context')
        self.assertIn('head', body['images'])
        self.assertNotIn('torso', body['images'])
        result.boxes.xyxy = torch.tensor([[0, 0, 400, 650], [0, 0, 390, 640]])
        result.keypoints.__len__.return_value = 2
        self.assertEqual(vision.body(person)['route'], 'person_only')

    def test_face_ranking_keeps_freshness_and_rejects_reused_evidence(self):
        rows = [{'captured': moment, 'quality': {'score': 2}, 'face_quality': {'score': score}}
                for moment, score in [(8, 100), (9.6, 2), (10, .1), (11, 100)]]
        self.assertIs(select_candidate(rows, 10, 9, prefer_face=True), rows[1])
        self.assertIs(select_candidate(rows, 10, 9), rows[2])
        self.assertIs(select_candidate(rows, 10, 9.6, prefer_face=True), rows[2])

    def test_head_png_roundtrip_and_request_manifest(self):
        image = np.random.default_rng(4).integers(0, 256, (80, 120, 3), dtype=np.uint8)
        encoded, extension = observation_image(image, 'head')
        self.assertEqual(extension, 'png')
        self.assertTrue(np.array_equal(cv2.imdecode(np.frombuffer(encoded, np.uint8), cv2.IMREAD_COLOR), image))
        policy = {'hood_required': True, 'closure_required': False}
        with patch.dict('os.environ', {'OPENAI_API_KEY': 'offline-test'}), \
                patch('chemiguard.decisions.httpx.post') as post:
            post.return_value.status_code = 400
            post.return_value.headers = {}
            result = observe({'person': image, 'head': image, 'identity_torso': image}, policy)
            request = json.loads(post.call_args.kwargs['content'])
        inputs = [part for part in request['input'][0]['content'] if part['type'] == 'input_image']
        self.assertEqual(len(inputs), 2)
        self.assertTrue(all(part['detail'] == 'original' for part in inputs))
        self.assertEqual(base64.b64decode(inputs[-1]['image_url'].split(',')[1]), encoded)
        self.assertEqual(result['image_inputs'][-1]['sha256'], hashlib.sha256(encoded).hexdigest())
        self.assertEqual(result['image_inputs'][-1]['width'], 120)
        self.assertIn('api_roundtrip', result['timings_ms'])
        self.assertEqual(result['wearing'], 'UNKNOWN')
        self.assertEqual(post.call_count, 1)


if __name__ == '__main__':
    unittest.main()
