-- ============================================================================
-- Emma AI · Phase 5 follow-up - solver agency fills must not outlive their roster
--
-- run_optimization() writes one agency_assignments purchase per synthetic fill,
-- always carrying shift_id + shift_assignment_id (optimize.py, "Synthetic solver
-- fills have both a roster cell and a linked purchase/cost record"). Both anchors
-- are ON DELETE SET NULL, so discarding an A/B/C draft did not remove its
-- purchases - it nulled their anchors instead.
--
-- external_workforce() reads an unlinked row as a legacy/direct vendor booking
-- and counts it period-scoped, so every discarded option permanently inflated
-- agency dependency and cost. Home A reached 77.8% dependency and HK$578k of
-- agency spend on a roster with ten staff and no agency workers at all.
--
-- A solver fill for a draft that no longer exists is a hypothetical that was
-- never worked and never paid, so it is deleted with its shift. Genuine bookings
-- keep ON DELETE SET NULL: that money really was spent and must survive a roster
-- edit. 'Emma auto-fill' is the marker run_optimization stamps on its own rows
-- and is the only provenance signal on this table - keep the two in step.
-- ============================================================================

create or replace function public.purge_autofill_agency_purchase()
returns trigger
language plpgsql
set search_path = public
as $$
begin
    delete from agency_assignments
    where shift_id = old.id
      and vendor = 'Emma auto-fill';
    return old;
end;
$$;

drop trigger if exists trg_purge_autofill_agency_purchase on shifts;
create trigger trg_purge_autofill_agency_purchase
before delete on shifts
for each row execute function public.purge_autofill_agency_purchase();

-- Reclaim the rows already orphaned by the old behaviour. The solver always sets
-- shift_id, so an 'Emma auto-fill' row without one is orphaned by definition.
delete from agency_assignments
where shift_id is null
  and vendor = 'Emma auto-fill';
