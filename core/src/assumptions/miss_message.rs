// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

// ABOUTME: The wording an assumption-table lookup refusal carries when keys miss.
// ABOUTME: Says what the lookup knows -- the keys it missed -- never a count or a frame row.

//! Refusal wording for assumption-table lookup misses.
//!
//! A lookup runs as an elementwise Polars expression plugin, and the engine
//! hands such a plugin one batch of rows per call. The whole call is the
//! exported key columns, the kwargs bytes, a slot for the return value and a
//! `CallerContext`; and `CallerContext` carries a single bitflag, PARALLEL
//! (`polars-ffi` 0.53.0, `src/version_0.rs`, `struct CallerContext`), which
//! `call_plugin` builds fresh at the call site (`polars-plan` 0.53.0,
//! `src/plans/aexpr/function_expr/plugin.rs`). No row offset reaches the
//! plugin, so a position counted while walking the batch is a position in the
//! batch and not a row of the frame. Under the default streaming engine the
//! two differ; under the in-memory engine they happen to agree, and the
//! plugin cannot tell which of the two it is running under.
//!
//! So this builder names the keys that missed and prints neither a row number
//! nor a count. A reader handed a key can filter the frame and find every row
//! that carries it; a reader handed the wrong row number opens the wrong model
//! point and finds nothing wrong with it. A count was printed once, worded as
//! the batch's, but a number beside a miss is read as the frame's however it
//! is worded, and the batch's is smaller than the frame's wherever the
//! streaming engine split the misses: the keys already find every
//! row, so the number is left out rather than qualified.
//!
//! # The first line is the stable part
//!
//! When `collect()` fails, `gaspatchio/errors/boundary.py` replays the
//! model's recorded calculations one at a time over a row-capped head of the
//! frame and names the one that raises the same error class with the same
//! FIRST LINE. The sampled keys vary with the batch: the streaming collect
//! samples the batch it was handed, the replay the head it was given, and a
//! miss scattered over a 50,000-row frame once produced two different first
//! lines for one failure -- so the column was never named at the scale where
//! it matters most. Line 1 therefore carries only what is the same under
//! every engine and every batch: the table and the key column names. The
//! sampled keys and the recipe follow on the next line. The plugin boundary prefixes line 1 with
//! `the plugin failed with message: `, which is constant too.
//!
//! # The router no longer reads these words
//!
//! It once did. `gaspatchio/errors/suggestions.py` chose the advice printed
//! beneath these messages by testing lowercased substrings in order, its
//! date/time branch ahead of the null/missing branch a lookup miss means to
//! reach, and one ordinary English word decided it: an earlier wording of
//! the sentence below said "one batch of rows at a **time**", and a
//! mortality lookup that missed at attained age 99 was answered with "Check
//! date format matches your data". That router now keys on the failing
//! calculation's own lowering -- a lookup IS a lookup whatever the sentence
//! says -- so rewording the message cannot move the advice beneath it.
//! The test below keeps the five words out anyway: the wording is better
//! without them, and it costs nothing to hold.

/// How many distinct missed keys a refusal names.
///
/// Enough to show a pattern -- one age, or an age and a duration that always
/// travel together -- and short enough that the sentence still reads. The
/// builder below enforces it itself, and de-duplicates first, so a caller
/// that hands over the same key three times still produces a message that
/// says what it shows.
pub const SAMPLE_KEY_CAP: usize = 3;

/// Build the refusal raised when a lookup key is not in the table.
///
/// `key_columns` names the key columns as the lookup received them, and
/// goes on the first line with the table: the two things about a miss that
/// are the same whichever batch reported it. `sample_keys` holds key
/// descriptions, each already spelled `name=value` and joined across the key
/// columns of one row; repeats are dropped and the first [`SAMPLE_KEY_CAP`]
/// survivors are named, because a batch that misses the same age forty times
/// has one key to report and printing it forty times reports nothing further.
/// The samples sit on the second line. No count is taken: the lookup sees one
/// batch, and a batch's count beside a miss is read as the frame's.
///
/// # Examples
///
/// ```
/// use gaspatchio_core_lib::assumptions::missing_keys_refusal;
///
/// let message = missing_keys_refusal(
///     "mortality",
///     &["attained_age"],
///     &["attained_age=77".to_string()],
/// );
/// let first_line = message.lines().next().unwrap_or_default();
/// assert!(first_line.contains("'mortality'"));
/// assert!(first_line.contains("'attained_age'"));
/// assert!(message.contains("attained_age=77"));
/// assert!(message.contains("one batch of rows per call"));
/// assert!(!message.contains("row 0"));
/// assert!(!message.contains("row(s)"));
/// ```
#[must_use]
pub fn missing_keys_refusal(
    table_name: &str,
    key_columns: &[&str],
    sample_keys: &[String],
) -> String {
    let mut shown: Vec<&str> = Vec::new();
    for key in sample_keys {
        if shown.len() == SAMPLE_KEY_CAP {
            break;
        }
        if !shown.contains(&key.as_str()) {
            shown.push(key);
        }
    }
    let samples = if shown.is_empty() {
        String::new()
    } else {
        let listed: String = shown.iter().map(|key| format!(" ({key})")).collect();
        format!("Missed keys (first {SAMPLE_KEY_CAP} distinct):{listed}. ")
    };
    let keyed = key_column_clause(key_columns);
    format!(
        "Lookup on table '{table_name}' has missing keys (or NaN-valued entries){keyed}.\n\
         {samples}The engine hands this lookup one batch of rows per call, so it can \
         say neither how many of the frame's rows missed nor which frame row -- filter \
         the frame on the keys above to find those rows. The keys named are the ones \
         this batch missed; other batches may miss different keys. Keys must exist in \
         the table (exact match). Pass on_missing=\"nan\" or a numeric fill value to \
         Table(...) or lookup(...) to restore silent-NaN behaviour."
    )
}

/// Spell the key columns for a refusal's first line: ` for key column 'age'`,
/// ` for key columns 'age', 'duration'`, or nothing when there are none.
///
/// Quoted, so a key column called `age duration` reads as one name; empty
/// when the caller had none, so the sentence around it still closes.
fn key_column_clause(key_columns: &[&str]) -> String {
    match key_columns {
        [] => String::new(),
        [only] => format!(" for key column '{only}'"),
        many => {
            let listed: Vec<String> = many.iter().map(|name| format!("'{name}'")).collect();
            format!(" for key columns {}", listed.join(", "))
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Does the message print a row number -- `row 0`, `row 2500` -- anywhere?
    ///
    /// Written as a scan rather than an equality because the defect this
    /// wording repairs was a number in the middle of a sentence, and the next
    /// one would be too. `row(s)` is not a row number and must not trip it.
    fn names_a_row_number(message: &str) -> bool {
        message.match_indices("row ").any(|(at, _)| {
            message[at + "row ".len()..]
                .chars()
                .next()
                .is_some_and(|c| c.is_ascii_digit())
        })
    }

    /// The first line of a refusal, which is what the replay matcher compares.
    fn first_line(message: &str) -> &str {
        message.split('\n').next().unwrap_or_default()
    }

    #[test]
    fn the_refusal_names_every_key_it_was_given() {
        let message = missing_keys_refusal(
            "mortality",
            &["age", "duration"],
            &[
                "age=77, duration=3".to_string(),
                "age=99, duration=0".to_string(),
            ],
        );

        assert!(message.contains("(age=77, duration=3)"), "{message}");
        assert!(message.contains("(age=99, duration=0)"), "{message}");
        assert!(message.contains("'mortality'"), "{message}");
    }

    #[test]
    fn the_refusal_never_prints_a_row_number_or_a_count() {
        // The row a lookup can count is the row of its batch, and under the
        // default streaming engine that is not the row of the frame. A number
        // the reader would take for a model point is the one thing this
        // message must not carry -- on any of its lines.
        let message = missing_keys_refusal(
            "mortality",
            &["attained_age"],
            &["attained_age=99".to_string()],
        );

        assert!(!names_a_row_number(&message), "{message}");
        assert!(!message.contains("row(s)"), "{message}");
    }

    #[test]
    fn no_count_is_stated_since_the_batch_s_would_read_as_the_frame_s() {
        // The plugin sees one batch, and a number beside a miss is
        // read as the frame's however it is worded. Streaming split three
        // misses into batches and reported 1 where the frame held 3. The
        // keys find every row, so no number is printed at all.
        let message = missing_keys_refusal("mortality", &["age"], &["age=99".to_string()]);
        let (_, rest) = message
            .split_once('\n')
            .unwrap_or_else(|| panic!("one line only: {message}"));

        assert!(
            rest.starts_with("Missed keys (first 3 distinct): (age=99). "),
            "{rest}"
        );
        assert!(!message.contains("row(s)"), "{message}");
        assert!(!message.contains("in the batch it was handed"), "{message}");
        assert!(
            message.contains("neither how many of the frame's rows missed"),
            "{message}"
        );
    }

    #[test]
    fn the_refusal_keeps_the_exact_match_rule_and_the_opt_out() {
        let message = missing_keys_refusal("mortality", &["age"], &["age=99".to_string()]);

        assert!(message.contains("exact match"), "{message}");
        assert!(message.contains(r#"on_missing="nan""#), "{message}");
    }

    #[test]
    fn the_refusal_points_at_the_move_that_replaces_the_row_number() {
        let message = missing_keys_refusal("mortality", &["age"], &["age=99".to_string()]);

        assert!(
            message.contains("filter the frame on the keys above to find those rows"),
            "{message}"
        );
    }

    #[test]
    fn the_recipe_says_the_keys_are_this_batchs_and_not_the_frames() {
        // The filter finds every row behind the misses this call reported, and
        // that is all it finds: when misses carry different keys across
        // batches, the next run reports a key this one never saw. An actuary
        // who fixes age=99, re-runs and meets age=88 is looking at the design
        // rather than at a second defect, and the sentence has to say so.
        let message = missing_keys_refusal("mortality", &["age"], &["age=99".to_string()]);

        assert!(
            message.contains("other batches may miss different keys"),
            "{message}"
        );
    }

    #[test]
    fn a_key_that_missed_many_times_is_named_once() {
        // With the row number gone, three misses on one age used to print
        // "(attained_age=99) (attained_age=99) (attained_age=99)" -- three
        // identical parentheticals where the row had distinguished them.
        let message = missing_keys_refusal(
            "mortality",
            &["attained_age"],
            &[
                "attained_age=99".to_string(),
                "attained_age=99".to_string(),
                "attained_age=99".to_string(),
            ],
        );

        assert_eq!(message.matches("(attained_age=99)").count(), 1, "{message}");
    }

    #[test]
    fn the_named_keys_stop_at_the_cap_and_keep_the_order_they_missed_in() {
        let keys: Vec<String> = ["99", "88", "88", "77", "66"]
            .iter()
            .map(|age| format!("attained_age={age}"))
            .collect();

        let message = missing_keys_refusal("mortality", &["attained_age"], &keys);

        assert!(
            message.contains("(attained_age=99) (attained_age=88) (attained_age=77)"),
            "{message}"
        );
        assert!(!message.contains("attained_age=66"), "{message}");
        assert!(
            message.contains(&format!("Missed keys (first {SAMPLE_KEY_CAP} distinct)")),
            "{message}"
        );
    }

    #[test]
    fn the_refusal_carries_no_word_that_re_routes_its_own_advice() {
        // History, kept for the wording's sake: the advice under this message
        // was once chosen by matching lowercased substrings in order, and "one
        // batch of rows at a time" was enough to answer a missing attained age
        // with "Check date format matches your data". The router keys on the
        // failing record now, so this pins the wording and no longer pins the
        // routing.
        let message = missing_keys_refusal(
            "mortality",
            &["attained_age"],
            &["attained_age=99".to_string()],
        );

        let lowered = message.to_lowercase();
        for word in ["date", "time", "timestamp", "datetime", "parse"] {
            assert!(!lowered.contains(word), "{word} in: {message}");
        }
    }

    #[test]
    fn a_lookup_with_no_samples_still_reads_as_a_sentence() {
        // Every miss path collects at least one sample today; the builder must
        // not leave a dangling colon if one ever does not.
        let message = missing_keys_refusal("mortality", &["age"], &[]);

        assert!(!message.contains("Missed keys (first"), "{message}");
        assert!(
            message.contains("entries) for key column 'age'.\nThe engine hands"),
            "{message}"
        );
        assert!(!names_a_row_number(&message), "{message}");
    }

    #[test]
    fn the_first_line_names_the_table_and_the_key_columns() {
        let message = missing_keys_refusal(
            "mortality",
            &["age", "duration"],
            &["age=99, duration=0".to_string()],
        );

        assert_eq!(
            first_line(&message),
            "Lookup on table 'mortality' has missing keys (or NaN-valued entries) for key \
             columns 'age', 'duration'."
        );
    }

    #[test]
    fn the_first_line_is_the_same_whatever_the_batch_sampled() {
        // The replay matcher in gaspatchio/errors/boundary.py compares first
        // lines. A streaming collect and an in-memory replay of the same miss
        // sample different keys; the line they are compared on must not know
        // that.
        let streamed = missing_keys_refusal("mortality", &["age"], &["age=99".to_string()]);
        let replayed = missing_keys_refusal(
            "mortality",
            &["age"],
            &[
                "age=88".to_string(),
                "age=99".to_string(),
                "age=77".to_string(),
            ],
        );

        assert_eq!(first_line(&streamed), first_line(&replayed));
        assert_ne!(streamed, replayed);
    }

    #[test]
    fn the_first_line_carries_no_sampled_key() {
        let message = missing_keys_refusal(
            "mortality",
            &["attained_age"],
            &["attained_age=99".to_string()],
        );
        let (line_one, rest) = message
            .split_once('\n')
            .unwrap_or_else(|| panic!("one line only: {message}"));

        assert!(!line_one.contains("attained_age=99"), "{line_one}");
        assert!(rest.contains("(attained_age=99)"), "{rest}");
    }

    #[test]
    fn a_single_key_column_reads_in_the_singular() {
        let message = missing_keys_refusal("mortality", &["age"], &["age=99".to_string()]);

        assert!(
            first_line(&message).ends_with("for key column 'age'."),
            "{message}"
        );
        assert!(!message.contains("key columns"), "{message}");
    }

    #[test]
    fn a_refusal_with_no_key_columns_still_closes_its_sentence() {
        // The plugin refuses a lookup with no key columns before any miss can
        // be found, so this is the builder's own contract rather than a
        // path a model reaches.
        let message = missing_keys_refusal("mortality", &[], &[]);

        assert_eq!(
            first_line(&message),
            "Lookup on table 'mortality' has missing keys (or NaN-valued entries)."
        );
    }
}
