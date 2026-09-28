{#
  Served concepts, each defined once here and referenced with doc() from
  every served column that uses it (#44 AC5). Change a definition here, never
  in a column's own description.
#}

{% docs ratified %}
**Ratified:** FPL has finalised this round's points, bonus included. The
value is sourced from FPL's `event-status` endpoint, not inferred from a
scoreline: scores appear at full time, but bonus is applied hours later, and
until then a row's `bonus` and `bps` are not final. It is a property of the
round, carried on each of its rows. A round is ratified when every one of its
match dates reads ratified in one capture, and it stays ratified once any
capture has said so. For a closed season it is true on every row.
{% enddocs %}

{% docs season_scoped_key %}
**Season-scoped key:** FPL reassigns this id every season, so the same value
in two seasons names two different things. Match it only together with
`season`, and filter or group by `season` before relying on it: an unfiltered
group-by silently merges two seasons' rows.
{% enddocs %}

{% docs pre_kickoff %}
**Pre-kickoff:** taken from the last capture before the fixture kicked off,
so it is the value a manager saw before the match and cannot reflect the
result. Where no capture precedes kickoff (all of 2025-26, one end-of-season
snapshot, and live fixtures played before capture history began on
2026-08-29), the earliest captured value is served instead and
`difficulty_is_pre_kickoff` is false.
{% enddocs %}
