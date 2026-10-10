"""Text from a tall capture: lines rebuilt from Tesseract's word positions."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vertorama import output  # noqa: E402

HEAD = "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext"


def word(block, par, line, top, text, height=20):
    return f"5\t1\t{block}\t{par}\t{line}\t1\t10\t{top}\t50\t{height}\t95\t{text}"


class TextTest(unittest.TestCase):
    def test_evenly_spaced_lines_have_no_blank_lines(self):
        # Tesseract splits these into separate paragraphs, which used to
        # show up as random blank lines.
        rows = [HEAD, word(1, 1, 1, 0, "one"), word(1, 1, 1, 0, "two"),
                word(1, 2, 1, 30, "three"), word(1, 3, 1, 60, "four")]
        lines = output.lines_from_tsv("\n".join(rows))
        self.assertEqual(output.join_lines(lines), "one two\nthree\nfour")

    def test_a_real_gap_keeps_a_blank_line(self):
        rows = [HEAD, word(1, 1, 1, 0, "Title"), word(1, 1, 2, 80, "first"), word(1, 1, 3, 110, "second")]
        self.assertEqual(output.join_lines(output.lines_from_tsv("\n".join(rows))), "Title\n\nfirst\nsecond")

    def test_empty_words_and_other_levels_are_skipped(self):
        rows = [HEAD, "4\t1\t1\t1\t1\t0\t0\t0\t100\t20\t-1\t", word(1, 1, 1, 0, " "), word(1, 1, 1, 0, "kept")]
        self.assertEqual(output.join_lines(output.lines_from_tsv("\n".join(rows))), "kept")

    def test_nothing_read(self):
        self.assertEqual(output.join_lines(output.lines_from_tsv(HEAD)), "")


if __name__ == "__main__":
    unittest.main()
