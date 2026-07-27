-- ============================================================================
-- Emma AI · split shifts (A/N)
--
-- The scheduling spec defines A/N as a SPLIT shift, not a long one:
--   Home A  07:00–13:30  and  21:30–07:00 next day   =  6.5h +  9.5h = 16h paid
--   Home B  07:00–14:30  and  21:15–07:15 next day   =  7.5h + 10.0h = 17.5h paid
--
-- Modelled as a single 07:00→13:30-next-day row it read as 30.5h elapsed, which
-- inflated every hours/OT figure, blocked cover suggestions on "would exceed max
-- hours", and counted the nurse as on duty through their unpaid afternoon rest.
--
-- `segments` holds the real duty windows; NULL means an ordinary contiguous
-- shift and behaves exactly as before. `paid_minutes` lets a facility pay a
-- handover or sleep-in differently from the clock. See emma_core/shifttime.py.
--
-- Columns only — the shift dictionary is facility-configured data, so the
-- correct segments per home are set by scripts/seed.py (and, for a live
-- facility, by whoever maintains shift_definitions).
-- ============================================================================

alter table shift_definitions add column if not exists segments jsonb;

alter table shifts add column if not exists segments     jsonb;
alter table shifts add column if not exists paid_minutes int;

comment on column shift_definitions.segments is
    'Split-shift duty windows: [{"start":"07:00","end":"13:30"},{"start":"21:30","end":"07:00"}]. NULL = one contiguous span from start_time/end_time.';
comment on column shifts.segments is
    'Duty windows copied from the shift definition when the shift was created.';
comment on column shifts.paid_minutes is
    'Paid duty minutes. NULL = derive from segments (or from start/end when there are none).';
