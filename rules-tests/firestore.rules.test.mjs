// Firestore security rules tests. Run against the local emulator only (demo- project id
// means no real Google project is ever touched).
import { readFileSync } from "node:fs";
import { after, before, beforeEach, test } from "node:test";
import {
  assertFails,
  assertSucceeds,
  initializeTestEnvironment,
} from "@firebase/rules-unit-testing";
import { collection, doc, getDoc, getDocs, query, setDoc, where } from "firebase/firestore";

let env;

before(async () => {
  env = await initializeTestEnvironment({
    projectId: "demo-proofcard",
    firestore: { rules: readFileSync(new URL("../firestore.rules", import.meta.url), "utf8") },
  });
});

after(async () => env.cleanup());

beforeEach(async () => {
  await env.clearFirestore();
  await env.withSecurityRulesDisabled(async (ctx) => {
    const db = ctx.firestore();
    await setDoc(doc(db, "sessions/s1"), { owner_uid: "alice", topic: "t" });
    await setDoc(doc(db, "sessions/s1/claims/c1"), { text: "x" });
    await setDoc(doc(db, "cards/card1"), { claim: "x", verdict: "TRUE" });
    await setDoc(doc(db, "tg_checks/k1"), { result: "ALTERED" });
  });
});

const as = (uid) => (uid ? env.authenticatedContext(uid) : env.unauthenticatedContext()).firestore();

test("owner reads own session and claims", async () => {
  await assertSucceeds(getDoc(doc(as("alice"), "sessions/s1")));
  await assertSucceeds(getDoc(doc(as("alice"), "sessions/s1/claims/c1")));
});

test("owner can list only own sessions", async () => {
  const db = as("alice");
  await assertSucceeds(getDocs(query(collection(db, "sessions"), where("owner_uid", "==", "alice"))));
  await assertFails(getDocs(collection(db, "sessions")));
});

test("other user and anonymous visitor cannot read a session", async () => {
  await assertFails(getDoc(doc(as("mallory"), "sessions/s1")));
  await assertFails(getDoc(doc(as("mallory"), "sessions/s1/claims/c1")));
  await assertFails(getDoc(doc(as(null), "sessions/s1")));
});

test("clients can never write", async () => {
  await assertFails(setDoc(doc(as("alice"), "sessions/s1"), { owner_uid: "alice", topic: "hacked" }));
  await assertFails(setDoc(doc(as("alice"), "sessions/s2"), { owner_uid: "alice" }));
  await assertFails(setDoc(doc(as("alice"), "cards/card1"), { verdict: "FALSE" }));
});

test("cards: public get, no listing", async () => {
  await assertSucceeds(getDoc(doc(as(null), "cards/card1")));
  await assertFails(getDocs(collection(as(null), "cards")));
});

test("server only collections are closed", async () => {
  await assertFails(getDoc(doc(as("alice"), "tg_checks/k1")));
  await assertFails(getDoc(doc(as(null), "jobs/j1")));
});
