"""Chunk boundaries must have no effect on market time or reconstructed state."""

import numpy as np
import pandas as pd
import pytest

from gqh.microdata import BAD_RECV, LAST, SNAPSHOT, Book, mbo_features, mbo_features_iter


def stream_fixture():
    rows = [
        (0, "R", "N", np.nan, 0, 0, SNAPSHOT | BAD_RECV),
        (0, "A", "B", 100, 10, 1, SNAPSHOT | BAD_RECV),
        (0, "A", "B", 100, 20, 3, SNAPSHOT | BAD_RECV),
        (0, "A", "A", 100.25, 10, 2, SNAPSHOT | BAD_RECV | LAST),
        (0.2, "N", "N", np.nan, 0, 0, LAST),
        (0.3, "C", "B", 100, 2, 3, LAST),
        (0.999, "T", "B", 100.25, 4, 9, 0),
        (0.999, "F", "A", 100.25, 4, 2, 0),
        (1.001, "M", "A", 100.25, 6, 2, LAST),
        (1.3, "M", "B", 100, 11, 1, LAST),
        (1.4, "C", "B", 100, 2, 3, LAST),
        (2.1, "T", "N", 100.25, 3, 0, LAST),
        (2.5, "R", "N", np.nan, 0, 0, SNAPSHOT),
        (2.5, "A", "B", 101, 15, 10, SNAPSHOT),
        (2.5, "A", "A", 101.25, 18, 11, SNAPSHOT | LAST),
        (2.7, "N", "N", np.nan, 0, 0, LAST),
        (3.2, "T", "A", 101, 5, 20, 0),
        (3.2, "F", "B", 101, 5, 10, 0),
        (3.2, "M", "B", 101, 10, 10, LAST),
        (4.1, "N", "N", np.nan, 0, 0, LAST),
    ]
    frame = pd.DataFrame(rows, columns=["seconds", "action", "side", "price", "size", "order_id", "flags"])
    frame.index = pd.Timestamp("2026-09-01T00:00:00Z") + pd.to_timedelta(frame.pop("seconds"), unit="s")
    frame.index.name = "ts_recv"
    frame["instrument_id"], frame["publisher_id"] = 123, 1
    return frame


def test_known_completed_bars_preserve_flow_priority_and_reset_semantics():
    result = mbo_features_iter([stream_fixture()])
    assert result.index.equals(pd.date_range("2026-09-01T00:00:01Z", periods=4, freq="s", name="ts_decision"))
    assert result.valid.tolist() == [False, True, False, True]
    assert result.bid.tolist() == [100, 100, 101, 101]
    assert result.ask_size.tolist() == [10, 6, 18, 18]
    assert result.bid_size.tolist() == [28, 27, 15, 10]
    assert result.trade_volume.tolist() == [0, 4, 0, 5]
    assert result.signed_volume.tolist() == [0, 4, 0, -5]
    assert result.bid_cancel.tolist() == [2, 2, 0, 0]
    assert result.bid_priority_cancel.tolist() == pytest.approx([2 / 11, 2, 0, 0])
    assert result.ask_cancel.sum() == 0
    assert result.bid_add.tolist() == [0, 1, 0, 0]


def test_every_single_split_matches_whole_replay_including_snapshot_and_event():
    frame = stream_fixture()
    whole = mbo_features(frame)
    for cut in range(len(frame) + 1):
        pd.testing.assert_frame_equal(mbo_features_iter([frame.iloc[:cut], frame.iloc[cut:]]), whole)


def test_every_record_can_be_its_own_chunk_without_finalizing_bars():
    frame = stream_fixture()
    actual = mbo_features_iter(frame.iloc[i:i + 1] for i in range(len(frame)))
    pd.testing.assert_frame_equal(actual, mbo_features(frame))


def test_one_pass_iterable_and_empty_chunks():
    frame = stream_fixture()

    class Once:
        calls = 0

        def __iter__(self):
            self.calls += 1
            assert self.calls == 1, "Streaming replay may not seek or restart its input"
            for left, right in ((0, 0), (0, 2), (2, 8), (8, 8), (8, 9), (9, 19), (19, 20), (20, 20)):
                yield frame.iloc[left:right]

    source = Once()
    pd.testing.assert_frame_equal(mbo_features_iter(source), mbo_features(frame))
    assert source.calls == 1


@pytest.mark.parametrize("field,value", [("instrument_id", 456), ("publisher_id", 2)])
def test_identity_change_across_chunks_fails(field, value):
    frame = stream_fixture()
    second = frame.iloc[12:].copy()
    second[field] = value
    with pytest.raises(ValueError, match="instrument_id/publisher_id"):
        mbo_features_iter([frame.iloc[:12], second])


def test_publisher_field_cannot_disappear_across_chunks():
    frame = stream_fixture()
    with pytest.raises(ValueError, match="instrument_id/publisher_id"):
        mbo_features_iter([frame.iloc[:12], frame.iloc[12:].drop(columns="publisher_id")])


def test_receive_clock_cannot_go_backward_across_chunks():
    frame = stream_fixture()
    second = frame.iloc[12:].copy()
    second.index -= pd.Timedelta("2s")
    with pytest.raises(ValueError, match="monotonic.*across chunks"):
        mbo_features_iter([frame.iloc[:12], second])


def test_max_bars_bounds_all_chunks_and_empty_time_gaps():
    frame = stream_fixture()
    with pytest.raises(ValueError, match="bounded sample"):
        mbo_features_iter([frame.iloc[:12], frame.iloc[12:]], max_bars=3)
    distant = frame.iloc[-1:].copy()
    distant.index += pd.Timedelta("1day")
    with pytest.raises(ValueError, match="bounded sample"):
        mbo_features_iter([frame.iloc[:12], distant], max_bars=10)


def test_unfinished_tail_is_ignored_but_error_surfaces_if_that_bar_completes():
    frame = stream_fixture()
    corrupt_tail = frame.iloc[-1:].copy()
    corrupt_tail["action"], corrupt_tail["side"], corrupt_tail["price"] = "C", "B", 101
    corrupt_tail["size"], corrupt_tail["order_id"] = 1, 9999
    # Both replays drop the [4s, 5s) tail, including its invalid update.
    pd.testing.assert_frame_equal(mbo_features_iter([frame.iloc[:-1], corrupt_tail]), mbo_features(frame))
    later = frame.iloc[-1:].copy()
    later.index += pd.Timedelta("1s")
    with pytest.raises(ValueError, match="unknown"):
        mbo_features_iter([frame.iloc[:-1], corrupt_tail, later])


def test_index_units_and_timezone_do_not_change_receive_clock():
    frame = stream_fixture()
    changed = frame.copy()
    changed.index = changed.index.tz_convert("America/New_York").as_unit("us")
    pd.testing.assert_frame_equal(mbo_features_iter([changed.iloc[:8], changed.iloc[8:]]), mbo_features(frame))


def test_no_complete_bar_or_no_records_is_an_error():
    frame = stream_fixture()
    with pytest.raises(ValueError, match="found 0"):
        mbo_features_iter([frame.iloc[:3], frame.iloc[3:5]])
    with pytest.raises(ValueError, match="Nonempty"):
        mbo_features_iter(iter(()))


def test_cached_depth_and_lazy_heap_remain_correct_through_level_reuse():
    book = Book()
    book.apply("A", "B", 100, 10, 1)
    book.apply("A", "A", 101, 10, 2)
    # Repeated off-touch level removal/recreation must not grow duplicate heap entries.
    for oid in range(3, 203):
        book.apply("A", "B", 99, 5, oid)
        book.apply("M", "B", 99, 3, oid)
        book.apply("C", "B", 99, 1, oid)
        book.apply("M", "B", 99.5, 7, oid)
        book.apply("C", "B", 99.5, 7, oid)
        for side in ("B", "A"):
            assert book.totals[side] == {price: sum(orders.values()) for price, orders in book.levels[side].items()}
    assert len(book.heaps["B"]) == len(book.heap_prices["B"]) == 3
    book.apply("C", "B", 100, 10, 1)
    assert np.isnan(book.quote()["bid"])
    assert not book.heaps["B"]
    book.apply("A", "B", 99, 4, 999)
    assert book.quote()["bid_size"] == 4
