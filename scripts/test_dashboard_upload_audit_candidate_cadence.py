import copy
import unittest
import dashboard_upload_audit as audit

class CandidateHistoryCadence(unittest.TestCase):
    def setUp(self):
        self.analysis={'as_of':'20261120','candidate_stocks':[],'final_picks':[],
                       'data_validation':{'recommendation_selection_complete':False}}
        self.payload={'through_recommendation_date':'20261120',
                      'summary':{'pending':0,'unavailable':0,'evaluated':1},
                      'records':[{'id':'one','recommendation_date':'20261119','outcome':'WIN'}]}
    def test_complete_history_has_no_new_daily_cohort(self):
        self.assertEqual(audit.completed_candidate_history_date(self.payload,self.analysis),audit.day('20261120'))
        self.assertFalse(self.analysis['data_validation']['recommendation_selection_complete'])
        state=audit.completion_state([{'id':'market-ai','issues':['RECOMMENDATION_SELECTION_INCOMPLETE']}])
        self.assertEqual(state['status'],'ACTION_REQUIRED')
    def test_new_nonempty_public_candidates_still_require_update(self):
        self.analysis['candidate_stocks']=[{'code':'000001'}]
        self.assertIsNone(audit.completed_candidate_history_date(self.payload,self.analysis))
    def test_newer_empty_publication_must_be_recorded(self):
        self.analysis['as_of']='20261124'
        self.assertIsNone(audit.completed_candidate_history_date(self.payload,self.analysis))
    def test_later_empty_publication_can_reuse_proven_last_cohort(self):
        self.analysis['as_of']='20261124'
        self.assertEqual(audit.completed_candidate_history_date(self.payload,self.analysis,'20261120'),audit.day('20261120'))
        self.assertIsNone(audit.completed_candidate_history_date(self.payload,self.analysis,'20261123'))
    def test_last_revision_for_each_day_controls_history(self):
        history=[{'as_of':'20261124','candidate_stocks':[]},{'as_of':'20261123','candidate_stocks':[]},
                 {'as_of':'20261123','candidate_stocks':[{'code':'earlier'}]},
                 {'as_of':'20261120','candidate_stocks':[{'code':'kept'}]}]
        self.assertEqual(audit.latest_nonempty_candidate_date(history),audit.day('20261120'))
    def test_older_backfill_cannot_replace_latest_cohort(self):
        history=[{'as_of':'20261110','candidate_stocks':[{'code':'old'}]},
                 {'as_of':'20261120','candidate_stocks':[{'code':'latest'}]}]
        self.assertEqual(audit.latest_nonempty_candidate_date(history),audit.day('20261120'))
    def test_pending_or_unavailable_history_still_requires_work(self):
        for outcome,key in [('PENDING','pending'),('DATA_UNAVAILABLE','unavailable')]:
            p=copy.deepcopy(self.payload);p['records'][0]['outcome']=outcome;p['summary'][key]=1
            self.assertIsNone(audit.completed_candidate_history_date(p,self.analysis))
    def test_misreported_summary_does_not_hide_pending_row(self):
        self.payload['records'][0]['outcome']='PENDING'
        self.assertIsNone(audit.completed_candidate_history_date(self.payload,self.analysis))
    def test_empty_duplicate_and_future_records_fail_closed(self):
        for records in [[],self.payload['records']*2,[{'id':'one','recommendation_date':'20261124','outcome':'WIN'}]]:
            p=copy.deepcopy(self.payload);p['records']=records;p['summary']['evaluated']=len(records)
            self.assertIsNone(audit.completed_candidate_history_date(p,self.analysis))

if __name__=='__main__':unittest.main()
