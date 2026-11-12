-- Personal instructions, feature requests and briefing preferences are stored in `memories` (personal.py, digest_prefs.py)
-- with their own subject types. The original check constraint only allowed startup / founder / mentor, so those inserts were
-- refused ("memories_subject_type_check") and nothing was saved. Run once in the Supabase SQL editor.
alter table memories drop constraint if exists memories_subject_type_check;
alter table memories add constraint memories_subject_type_check
  check (subject_type in ('startup', 'founder', 'mentor', 'behavior', 'feature_request', 'digest_prefs'));
