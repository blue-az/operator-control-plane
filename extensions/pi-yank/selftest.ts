// Pure-logic selftest for pi-yank. Does not import pi.
//
//   node --experimental-strip-types extensions/pi-yank/selftest.ts

import { parseYankArgs, selectMessage, sliceMessage, textFromMessage } from "./core.ts";

let passed = 0;
let failed = 0;

function check(name: string, condition: unknown, detail = ""): void {
	if (condition) {
		passed += 1;
		console.log(`  ok  ${name}`);
	} else {
		failed += 1;
		console.log(`  FAIL ${name}${detail ? ` -- ${detail}` : ""}`);
	}
}

function eq<T>(name: string, actual: T, expected: T): void {
	check(name, JSON.stringify(actual) === JSON.stringify(expected), `got ${JSON.stringify(actual)}`);
}

console.log("pi-yank selftest (core.ts, no pi import)");

eq("empty args", parseYankArgs(""), {});
eq("undefined args", parseYankArgs(undefined), {});
eq("~2 only", parseYankArgs("~2"), { number: 2 });
eq("start only", parseYankArgs("hello"), { start: "hello" });
eq("start and end", parseYankArgs("hello world"), { start: "hello", end: "world" });
eq("quoted start with space", parseYankArgs('"hello world" end'), {
	start: "hello world",
	end: "end",
});
eq("~N then quoted anchors", parseYankArgs('~3 "start here" "end there"'), {
	number: 3,
	start: "start here",
	end: "end there",
});
eq("single-quoted anchor", parseYankArgs("'a b' c"), { start: "a b", end: "c" });

try {
	parseYankArgs("a b c");
	check("too many anchors throws", false, "did not throw");
} catch (err) {
	check(
		"too many anchors throws",
		err instanceof Error && err.message.includes("too many anchors"),
		String(err),
	);
}

const text = "alpha beta gamma beta omega";
eq("whole message", sliceMessage(text), { ok: true, slice: text });
eq("start to end of message", sliceMessage(text, "beta"), {
	ok: true,
	slice: "beta gamma beta omega",
});
eq("first-match start to first end after it", sliceMessage(text, "beta", "beta"), {
	ok: true,
	slice: "beta gamma ",
});
eq("missing start names the anchor", sliceMessage(text, "nope"), {
	ok: false,
	reason: 'start anchor not found: "nope"',
});
eq("missing end names the anchor", sliceMessage(text, "alpha", "nope"), {
	ok: false,
	reason: 'end anchor not found after start: "nope"',
});
eq("empty slice fails closed", sliceMessage(""), {
	ok: false,
	reason: "message has no text to yank",
});
eq("no case folding", sliceMessage("Hello", "hello"), {
	ok: false,
	reason: 'start anchor not found: "hello"',
});

eq("string content", textFromMessage({ role: "assistant", content: "hi" }), "hi");
eq(
	"text parts joined",
	textFromMessage({
		role: "assistant",
		content: [
			{ type: "text", text: "one" },
			{ type: "toolCall", text: "ignored" },
			{ type: "text", text: "two" },
		],
	}),
	"one\n\ntwo",
);
eq(
	"bashExecution",
	textFromMessage({ role: "bashExecution", command: "ls", output: "a\nb" }),
	"$ ls\na\nb",
);
eq("empty object", textFromMessage({ role: "assistant" }), "");

const msgs = [
	{ role: "user", text: "q" },
	{ role: "assistant", text: "first" },
	{ role: "user", text: "q2" },
	{ role: "assistant", text: "second" },
];
const latest = selectMessage(msgs);
check("default latest assistant", latest.ok && latest.target.text === "second");
const n1 = selectMessage(msgs, 1);
check("~1 is newest assistant", n1.ok && n1.target.text === "second");
const n2 = selectMessage(msgs, 2);
check("~2 is previous", n2.ok && n2.target.text === "q2");
check("out of range ~9 fails closed", !selectMessage(msgs, 9).ok);
check("~0 fails closed", !selectMessage(msgs, 0).ok);
check("empty list fails closed", !selectMessage([], 1).ok);

console.log(`\n${passed} passed, ${failed} failed`);
if (failed > 0) process.exit(1);
