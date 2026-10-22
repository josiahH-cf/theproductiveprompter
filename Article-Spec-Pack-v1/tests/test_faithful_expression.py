"""Faithful expression: readers understand the author's meaning without persuasion, invented evidence or a house attitude."""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import editorial_context as context
import editorial_workbench as workbench
from test_article_flow_v3 import TemporaryRuntime, call, af

# A synthetic paraphrase shaped like the Dot acceptance case. It is fixture text, not a record of the author's statement.
DOT_SEED = """Dot as Her, or what Siri was supposed to become

Fixture account: we booked a flight through one simple conversation. It asked clarifying questions, used browser control, did what I asked, and a confirmation email arrived. That was amazing.

Fixture account: this is not AGI in the technical sense, but it is what we wanted Siri to be.

Fixture instruction: no diagrams and no extra material.
"""

# Two published paragraphs from the Dot baseline: the failure-first opening and the callback ending.
DOT_ARTICLE = """---
title: "Dot as Her, or what Siri was supposed to become"
---

A phone-call handoff while using my dot failed, and I do not know why. It mattered because continuity had already become the useful part of the experience.

My experience with my dot is useful and unfinished at the same time. I do not need it to seem human. I need the next handoff to work.
"""

DOT_UNDERSTANDING = ("A completed real-world flight booking through a natural conversation, with clarifying questions, browser "
                     "control and a confirmation email, made the assistant feel like the practical AI the author hoped Siri would become; "
                     "not a claim of technical AGI or consciousness.")


class FaithfulExpressionTests(TemporaryRuntime):
    def start(self, seed=DOT_SEED):
        code, payload = call(af.command_start, seed=seed, seed_file=None, slug=None)
        self.assertEqual(code, 0)
        return af.load_run(payload["run_id"])

    def intent(self, run, **changes):
        value = {"intent_schema_version": "1.0.0", "run_id": run["run_id"], "reader": "Curious readers of personal AI use",
                 "reader_job": "Understand why the booking changed the author's sense of an assistant", "purpose": "Explain",
                 "scope": "One author-reported booking", "position": None, "explicit_seed_content": [], "assumptions": [], "remaining_unknowns": [],
                 "core_idea": "Useful practical AI assistance arrived in the form the author wanted Siri to become.",
                 "intended_understanding": DOT_UNDERSTANDING,
                 "firsthand_evidence": [{"source": "seed", "exact_excerpt": "used browser control, did what I asked, and a confirmation email arrived",
                                         "supported_use": "The completed booking", "limits": "Author-reported; no airline, route, price or email contents supplied"}],
                 "author_tone": {"attitude": "Excited", "source": "seed", "exact_excerpt": "That was amazing."}}
        value.update(changes)
        return value

    def approve(self, directory, run, value):
        self.record_json(directory, run, "intent", value)
        return af.load_run(run["run_id"])

    def test_dot_contract_projects_exact_author_meaning_to_writing_context(self):
        directory, run = self.start()
        self.assertTrue(context.understanding_enabled(run))
        directory, run = self.approve(directory, run, self.intent(run))
        projected = af.load_json(Path(context.prepare(af, directory, run, "DRAFT", [])[0]["path"]))["contract"]
        self.assertEqual(projected["intended_understanding"], DOT_UNDERSTANDING)
        self.assertEqual(projected["firsthand_evidence"][0]["exact_excerpt"],
                         "used browser control, did what I asked, and a confirmation email arrived")
        self.assertEqual(projected["author_tone"]["exact_excerpt"], "That was amazing.")
        self.assertIn("never invent dialogue", projected["evidence_policy"].lower())
        self.assertIn("reported success", projected["qualification_policy"])
        self.assertEqual(projected["author_constraints"][0]["exact_text"], DOT_SEED)
        self.assertEqual(projected["precedence"].split(" > ")[0], "current explicit author request")

    def test_firsthand_evidence_and_tone_must_quote_the_author(self):
        directory, run = self.start()
        self.assertEqual(context.intent_meaning_findings(af, directory, run, self.intent(run), "intent"), [])
        invented = self.intent(run, firsthand_evidence=[{"source": "seed", "exact_excerpt": "I booked a Delta flight to Denver for $412", "supported_use": "Booking"}],
                               author_tone={"attitude": "Wry", "source": "seed", "exact_excerpt": "I was mildly amused by the assistant"})
        findings = context.intent_meaning_findings(af, directory, run, invented, "intent")
        self.assertEqual({f["location"] for f in findings}, {"firsthand_evidence[0]", "author_tone"})
        self.assertTrue(all(f["repair_state"] == "INTENT_REVIEW" for f in findings))
        wrong_source = self.intent(run, firsthand_evidence=[{"source": "revision-request", "exact_excerpt": "used browser control", "supported_use": "Booking"}])
        self.assertEqual(len(context.intent_meaning_findings(af, directory, run, wrong_source, "intent")), 1)
        missing = {k: v for k, v in self.intent(run).items() if k not in context.UNDERSTANDING_OUTPUTS["INTENT_REVIEW"]}
        self.assertEqual(len(context.intent_meaning_findings(af, directory, run, missing, "intent")), 4)
        path = self.record_json(directory, run, "intent-candidate", invented, "invented.json")
        outcome, gate = af.automatic_gate(directory, run, "INTENT_REVIEW", path)
        self.assertEqual(outcome, "REPAIR")
        self.assertIn("author_meaning_source", {f["criterion"] for f in gate})
        self.assertEqual(af.effective_repair_state(af.state_definition("INTENT_REVIEW", run), gate), "INTENT_REVIEW")

    def test_recorded_author_clarification_is_a_valid_firsthand_source(self):
        directory, run = self.start()
        self.record_json(directory, run, "author-context", {"responses": [{"exact_author_response": "I said theproductiveprompter.com under my breath and it caught it."}]})
        directory, run = af.load_run(run["run_id"])
        value = self.intent(run, firsthand_evidence=[{"source": "author-context", "exact_excerpt": "I said theproductiveprompter.com under my breath",
                                                      "supported_use": "Voice naturalness", "limits": "No transcript or system response supplied"}])
        self.assertEqual(context.intent_meaning_findings(af, directory, run, value, "intent"), [])

    def test_explanatory_and_reference_articles_need_no_position_tone_or_anecdote(self):
        cases = {
            "explanatory": ("Is alignment just whether an AI acted as intended, or should it include refusing unsafe instructions? I am not sure.",
                            {"core_idea": "Whether alignment should include refusing unsafe instructions is an open question.",
                             "intended_understanding": "The reader can explain both working definitions and why the question stays open."}),
            "reference": ("Share Research Runner with links and implementation steps.",
                          {"core_idea": None, "intended_understanding": "The reader can locate and follow the documented setup steps."}),
        }
        for name, (seed, meaning) in cases.items():
            with self.subTest(name=name):
                directory, run = self.start(seed)
                value = self.intent(run, position=None, firsthand_evidence=[], author_tone=None, **meaning)
                path = self.record_json(directory, run, "intent-candidate", value, f"{name}.json")
                self.assertEqual(af.automatic_gate(directory, run, "INTENT_REVIEW", path), ("PASS", []))
                directory, run = self.approve(directory, run, value)
                projected = context.contract(af, directory, run)
                self.assertIsNone(projected["authorized_position"])
                self.assertIsNone(projected["author_tone"])
                self.assertEqual(projected["firsthand_evidence"], [])
                self.assertIn("null imposes no attitude", projected["tone_policy"])
                self.assertIn("explanatory, exploratory or reference", projected["comprehension_policy"])
        recipe = context.UNDERSTANDING["ARTICLE_RECIPE"]
        self.assertIn("Do not impose first person, enthusiasm, an argument arc, a diagram or a word band", recipe)
        self.assertIn("a null strategy is valid", recipe)
        self.assertIn("No mandatory thesis sentence", context.UNDERSTANDING["DEVELOPMENT_REVIEW"])

    def comprehension(self, **changes):
        value = {"reader_paraphrase": "A handoff failed and the author wants continuity to work next time.",
                 "intended_understanding": DOT_UNDERSTANDING, "status": "REPAIR",
                 "evidence": [{"excerpt": "A phone-call handoff while using my dot failed", "role": "displaces"}],
                 "omissions_or_misreadings": ["The successful booking is absent; a reader would conclude the assistant failed."],
                 "repair_owner": "DRAFT", "reason": "The failure-first frame and callback ending replace the booking's meaning."}
        value.update(changes)
        return {"outcome": "REPAIR", "comprehension_review": value}

    def qa_run(self):
        directory, run = self.start()
        directory, run = self.approve(directory, run, self.intent(run))
        self.record_text(directory, run, "article", DOT_ARTICLE)
        return af.load_run(run["run_id"])

    def test_dot_misreading_routes_missing_meaning_to_draft_and_obscuring_prose_to_edit(self):
        directory, run = self.qa_run()
        [draft] = context.comprehension_findings(af, directory, run, self.comprehension(), "qa")
        self.assertEqual((draft["criterion"], draft["repair_state"], draft["location"]), ("comprehension_development", "DRAFT", "paragraph 1"))
        self.assertIn("booking is absent", draft["finding"])
        self.assertIn("Do not invent experience", draft["repair_instruction"])
        self.assertEqual(af.editorial_repair_destination(draft), "DRAFT")
        [edit] = context.comprehension_findings(af, directory, run, self.comprehension(
            repair_owner="EDIT", evidence=[{"excerpt": "I need the next handoff to work.", "role": "obscures"}]), "qa")
        self.assertEqual((edit["criterion"], edit["repair_state"], edit["location"]), ("comprehension_clarity", "EDIT", "paragraph 2"))
        self.assertEqual(af.editorial_repair_destination(edit), "EDIT")
        clean = self.comprehension(status="PASS", evidence=[{"excerpt": "I need the next handoff to work.", "role": "explains"}])
        self.assertEqual(context.comprehension_findings(af, directory, run, clean, "qa"), [])

    def test_comprehension_review_needs_current_excerpts_and_the_approved_target(self):
        directory, run = self.qa_run()
        no_owner = self.comprehension()
        no_owner["comprehension_review"].pop("repair_owner")
        cases = {
            "missing": {"outcome": "PASS"},
            "invented excerpt": self.comprehension(status="PASS", evidence=[{"excerpt": "The flight booking was insane", "role": "shows"}]),
            "moved target": self.comprehension(status="PASS", intended_understanding="The reader agrees that dots are useful."),
            "no owner": no_owner,
            "unlocated prose repair": self.comprehension(repair_owner="EDIT", evidence=[{"excerpt": "Dot as Her, or what Siri", "role": "obscures"}]),
        }
        for name, value in cases.items():
            with self.subTest(name=name):
                findings = context.comprehension_findings(af, directory, run, value, "qa")
                self.assertTrue(findings)
                self.assertTrue(all(f["repair_state"] == "EDITORIAL_QA" for f in findings), findings)

    def test_development_takeaway_must_agree_with_outcome_and_quote_the_draft(self):
        directory, run = self.qa_run()
        takeaway = {"paraphrase": "A handoff failed and the author wants continuity.", "intended_understanding": DOT_UNDERSTANDING, "status": "REPAIR",
                    "passages": [{"excerpt": "I need the next handoff to work.", "role": "displaces"}],
                    "gaps": [{"issue": "The completed booking is not in the draft", "cause": "insufficient_supplied_evidence"}]}
        findings = context.takeaway_findings(af, directory, run, {"outcome": "PASS", "reader_takeaway": takeaway}, DOT_ARTICLE, "review")
        self.assertEqual([(f["criterion"], f["repair_state"]) for f in findings], [("development", "DRAFT")])
        self.assertIn("completed booking", findings[0]["finding"])
        self.assertIn("rather than invent", findings[0]["repair_instruction"])
        self.assertEqual(context.takeaway_findings(af, directory, run, {"outcome": "REPAIR", "reader_takeaway": takeaway}, DOT_ARTICLE, "review"), [])
        invented = copy.deepcopy(takeaway)
        invented["passages"][0]["excerpt"] = "We booked a flight together."
        self.assertEqual(context.takeaway_findings(af, directory, run, {"outcome": "REPAIR", "reader_takeaway": invented}, DOT_ARTICLE, "review")[0]["repair_state"], "DEVELOPMENT_REVIEW")
        missing = context.takeaway_findings(af, directory, run, {"outcome": "PASS"}, DOT_ARTICLE, "review")
        self.assertEqual(missing[0]["repair_state"], "DEVELOPMENT_REVIEW")

    def frozen_before_understanding(self, directory, run):
        definitions = copy.deepcopy(run["definition_snapshot"]["value"])
        for name, fields in (("intent.schema.json", context.UNDERSTANDING_OUTPUTS["INTENT_REVIEW"]),
                             ("development-review.schema.json", ["reader_takeaway"]),
                             ("editorial-assessment.schema.json", ["comprehension_review"])):
            for field in fields:
                definitions["schemas"][name]["properties"].pop(field)
        run["definition_snapshot"] = {"value": definitions, "sha256": context.digest(definitions)}
        af.save_run(directory, run)
        return af.load_run(run["run_id"])

    def test_runs_frozen_before_this_change_keep_their_contract_guidance_and_gates(self):
        directory, run = self.start()
        directory, run = self.frozen_before_understanding(directory, run)
        self.assertFalse(context.understanding_enabled(run))
        legacy = {k: v for k, v in self.intent(run).items() if k not in context.UNDERSTANDING_OUTPUTS["INTENT_REVIEW"]}
        path = self.record_json(directory, run, "intent-candidate", legacy)
        self.assertEqual(af.automatic_gate(directory, run, "INTENT_REVIEW", path), ("PASS", []))
        directory, run = self.approve(directory, run, legacy)
        projected = context.contract(af, directory, run)
        self.assertNotIn("intended_understanding", projected)
        self.assertEqual(projected["stopping_condition"], "Reader can understand the supported reasoning or perform the requested task; remove redundant development.")
        for stage in ("INTENT_REVIEW", "DRAFT", "DEVELOPMENT_REVIEW", "EDITORIAL_QA"):
            self.assertEqual(context.constraints(stage), context.constraints(stage, False))
            self.assertNotIn(context.UNDERSTANDING[stage], context.constraints(stage))

    def test_offline_material_without_a_target_keeps_its_prepared_packet_guidance(self):
        root = workbench.workspace(af, str(self.root / "offline"))
        material = {"reader_job": "Explain the fixture", "facts": ["Review rejected rows before export."]}
        packet = af.load_json(Path(workbench.assist(af, root, "reader", material, execute=False, requested=None)["packet"]))
        self.assertNotIn(context.UNDERSTANDING["EDITORIAL_QA"], packet["constraints"])
        targeted = af.load_json(Path(workbench.assist(af, root, "reader", {**material, "intended_understanding": DOT_UNDERSTANDING}, execute=False, requested=None)["packet"]))
        self.assertIn(context.UNDERSTANDING["EDITORIAL_QA"], targeted["constraints"])
