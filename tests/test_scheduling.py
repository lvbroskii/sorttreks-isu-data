"""Trigger registration recovery does not change source collection or campaign guards."""
import json,re,unittest
from pathlib import Path
from datetime import datetime,timezone
from isu_pilot.monitor import plan
ROOT=Path(__file__).resolve().parents[1]
class SchedulingTests(unittest.TestCase):
 def test_primary_cron_keeps_exact_half_hour_slots_and_finite_month_days(self):
  workflow=(ROOT/'.github/workflows/pilot.yml').read_text()
  crons=re.findall(r"cron: '([^']+)'",workflow)
  self.assertEqual(crons[:2],['17/30 * 29-31 10 *','17/30 * 1-2 11 *'])
  # POSIX start/step expands through the end of the minute field: 17,47.
  self.assertEqual(list(range(17,60,30)),[17,47])
  self.assertIn("vars.ENABLE_PILOT == 'true'",workflow)
  self.assertIn("github.ref == 'refs/heads/main'",workflow)
  self.assertIn('cancel-in-progress: false',workflow)
  self.assertIn('Persist evidence even after a collector error',workflow)
 def test_diagnostic_trigger_cannot_override_campaign_stop(self):
  config=json.loads((ROOT/'config/monitoring.json').read_text())
  self.assertEqual(config['endsAt'],'2026-11-02T18:00:00Z')
  for now in ['2026-11-02T18:00:00+00:00','2027-10-29T16:03:00+00:00']:
   self.assertEqual(plan(config,{},datetime.fromisoformat(now)),'outside-campaign-window')
 def test_no_push_collection_and_explicit_native_trigger_evidence(self):
  workflow=(ROOT/'.github/workflows/pilot.yml').read_text()
  self.assertNotIn('\n  push:',workflow)
  self.assertIn('PILOT_EVENT_NAME: ${{ github.event_name }}',workflow)
  self.assertIn('PILOT_SCHEDULE: ${{ github.event.schedule }}',workflow)
  self.assertEqual(workflow.count('python3 -m isu_pilot monitor '),1)
