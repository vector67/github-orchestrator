# Exports grilling record

Each question from the session on minimising module exports, the recommendation that came with it, the answer given, and what was settled. Answers are quoted with filler words such as "um" and "uh" removed and nothing else changed; where a question took more than one exchange, every reply is included in order.

The opening request: rewrite the dependency page around the goal of minimising dependencies, fix settings' path leak straight away, and grill the exports down to about five per module, ten for an exceptional one.

## Q1 — What does the 5-per-module budget count: exports, imports, or both?

Recommended: Both, with exports the hard rule and imports counted as modules.

> I'm talking about exports right now, not imports. having lots of imports is fine because it just means that a module has many dependencies, there shouldn't be too many modules that have lots of dependencies, but a hub and spoke dependency graph is actually fine.

Settled: The budget counts exports. Many imports are fine; hub and spoke is fine.

## Q2 — Do the methods on a module's main object count toward the 5?

Recommended: Count names and methods separately, capping methods at about 10.

> The methods on a module's main object do not count towards the five. But there should be a separate cap that we put on the number of methods that the module's main object can have. I think we should potentially think about that as like... Yeah, I think your cap of 10 makes sense. But yeah, let's look at PR threads a little bit more in depth. Like you gave me in the document the list of things that are exported and I'd love to see the list of methods that are exported with something about what each one does and especially who uses it so that we can decide what is reasonable.

Settled: Methods don't count toward 5; each object is capped at about 10 methods.

## Q3 — Trim one PrThreads, or split it by caller?

Recommended: Split by caller, handed out by ReviewThreads.

> So I like the idea of splitting by caller, but I'm a little bit confused by what your plan is with this, because I agree that three independent callers, especially like this, should have three independent interfaces into the PR threads module. That makes a lot of sense. And even potentially the board should have two. It should have the writing and the reading. I mean, that would make a lot of sense. So in other words, there would actually be four, four different interfaces to the PR threads module. What I'm worried about though, is that the structure of the PR threads module is going to devolve because we have four interfaces. And so they're gonna kind of duplicate, conflict with each other. And, and that's the thing that I want to avoid. Otherwise, I really like the idea of splitting by caller. That way, each use thing has only like one or two a couple of exports, or a couple of methods, sorry, and I like that a lot. Yes, yeah, so you say decide is only used by the preview. what is the preview, and why do you say no real caller? like, how is that a fake caller? Yeah, now exists so callers can timestamp commands when review threads could stamp them itself. Absolutely, please do that. And then has commit and file at, you say it passes straight through to git. Now this is worrying for me because git has its own module. So are you telling me that PR threads touches git when it's not supposed to?

Settled: Split into several interfaces. PrThreads.now removed (merged as a9f36830).

## Q4 — What keeps the interfaces from drifting apart?

Recommended: One implementation class behind several narrow Protocols.

> I want the handles can compose because I'm not actually so worried about drift because the application logic quote unquote of the module is actually inside that application file and so the fact that the different external faces compose different parts of that application that actually makes a lot of sense.

Settled: Handles may compose application functions.

## Q5 — Do the handle types count toward review threads' budget?

Recommended: They count, and review threads is the exceptional module at 10.

> yeah they count and review threads is the exceptional module I agree why did the now change not get merged please merge please do all the stuff that you're supposed to do with a normal workflow

Settled: They count; review threads may have up to 10. The now change was merged and restarted.

## Q6 — What happens to the 43 string constants?

Recommended: Questions where callers decide, enums where the words are the product.

> so these should really just go into enums. oh, I see, I see. Yes, yes, I agree with you. Questions where the caller decides and enums where the words of the product. Yes, absolutely. because we don't, yeah, we don't need to reveal vocabulary that actually doesn't mean anything. Or at least doesn't, is only used to make a decision. because then we can just ask for that decision to be made.

Settled: Questions for decisions; enums only for words that are shown or sent.

## Q7 — What happens to the 22 exported command classes?

Recommended: Methods on the handles; the board's writes split in two.

> this is not making that much sense to me. I don't understand how the things connect. so you're saying what happens to the 22 exported command classes? Who exports those command classes? And what are they used for? Give me one example and give it to me from start to finish, like the user action that then causes this to happen, then that, then that, then the command, and then this happens, and this is the if statement and whatever. yeah, I, I don't actually get it at all,

> To be honest, this feels like a stylistic choice. if the consumer builds a domain object of its dependency in order to ask a question, that's the same as calling a method with the parameters. It's totally a stylistic choice. I think my preference is methods, as you said.

Settled: Methods; the command classes become private.

## Q8 — Where does the board get its git reads?

Recommended: has_commit and file_at straight from working copies; proposal_diff stays.

> Yeah, the board should definitely get git reads from working copies, since logically that's what it actually needs is from working copies. The the threads and the thread reviews are not logically where git stuff lives, so

Settled: The board reads git through working copies.

## Q9 — Does proposal_diff move to working copies, with review threads only naming the range?

Recommended: Yes: the fix answers its commit range and the containers go.

> Does anything else in the repository do anything with Git itself besides working copies?

> and proposal diff that feels like an object that belongs in a module is that true is it a, a an object that belongs in a module. Yeah, okay, those are all fine in terms of where Git lives. So, yeah, I think working copies makes the most sense. But I would like to understand where proposal diff lives where the concept of it lives

> Yeah, I would agree with this.

Settled: The fix answers its commit range; CommitDiff, ProposedChange and their methods go.

## Q10 — What does review threads give the board to read?

Recommended: The domain objects, with fewer names.

> this is difficult. Yeah, I think domain objects with fewer names, but to be honest, I, I don't want the interface of one module to be strictly defined by the requirements of another module. You know, the way that I said that the backend API shouldn't be determined by the frontend's needs. Instead, it should reveal it in a logical kind of domain-driven way. And then if there's something missing, that the front-end needs, then we consider, well, should we be adding this or not? that's kind of what I'm thinking about. So yeah, I think domain objects yeah, and if necessary, we can make a DTO that is the boundary. So it's like a domain object, but it's got a bit of stuff removed and added. In order to not reveal too many internals of the module.

Settled: Domain objects in the module's own terms; a DTO at the boundary when needed.

## Q11 — Are the handles split by caller or by domain role?

Recommended: By domain role: Upkeep, FixReports, Decisions, Drafts, Reading.

> Yes, absolutely. I think domain role, that is what more what I'm looking for.

Settled: Domain roles.

## Q12 — Which roles do check_later and mark_seen go in?

Recommended: check_later to Upkeep, mark_seen to Decisions.

> That makes sense.

Settled: As recommended.

## Q13 — What happens to ReviewThreads' own methods?

Recommended: poll to Upkeep, list to Reading, migrate deleted, prompt fragments deferred.

> Yep, agreed. Yeah, cool. That's good.

Settled: As recommended.

## Q14 — How do refusals cross the boundary?

Recommended: One refusal type with domain codes only.

> yeah, one refusal type domain codes only.

Settled: One Denied type; HTTP-only codes move to the board.

## Q15 — Which two names go to get review threads to 10?

Recommended: LineAnchor and UnreadableRecord.

> yeah, I agree. Just line anchor and unreadable record get dropped.

Settled: Both dropped.

## Q16 — How does notifications ask review threads what's still news?

Recommended: Review threads implements notifications' protocol.

> Okay, so this feels a little bit like notifications is a bigger module than I would expect. Could you just give me a quick rundown of how this actually works from a like call stack and trace point of view? In terms of the interaction between review threads and notifications and how notification actually lands in my notifications box from an action that has happened.

> Sounds great. There's only one thing that I would say is, is a little bit off. and that's the fact that the places that use the notifications decide whether they call gather or post. And that's a problem. there should be one notification method of the notifications. And then it's the notifications module's job to determine which kind of notification this is and the rules that apply. I don't want the notification rules to be distributed across the whole system. and, you know, like then I have to figure out, okay, well, when does this notification happen? And then I have to go and find the place that calls the notification. Yeah, notification module must decide everything here. Now, based on that, I think to answer the previous question, notification must be the module that's imported. with the notification type, like the class, whatever is defined with the data class, or whatever notification looks like, that needs to be imported from the other modules that use it. And then they construct their notification according to their specifications and then they send that to notification module. Does that answer the question? Or because I, I can't read it right now.

Settled: Producers import notifications' types; notifications decides everything; still-news is a protocol notifications defines.

## Q17 — Does notifications also write the wording?

Recommended: Yes: callers send facts.

> So I think yes. I'm only worried that certain of the like haiku summary stuff would then need to move into notifications, which would be fine. But I want to make sure that we don't duplicate effort here.

Settled: Notifications writes wording and picks the badge.

## Q18 — Who owns summarising a comment in one line?

Recommended: Review threads, putting the gist on the notification.

> actually, I think notification should be the one that does this because, yeah, I like the idea of other people only putting facts into the notification. And one of those facts could be, oh, yeah, we've already run a gist on this comment and this is the gist. That's perfectly valid as a fact that goes into a notification. But in general, if the gist hasn't been run and there isn't that fact already available, the notification should be the one that summarizes the comment into a notification or multiple comments into a notification. and, yeah, that makes sense.

Settled: Notifications summarises; a producer may pass an existing gist as a fact.

## Q19 — What's the rule for who writes an agent prompt?

Recommended: Each module writes its own; agent runs adds machine-wide rules.

> no. I disagree. So agent runs needs to have an interface which allows another client to get a specific job done. So for instance, agent runs will have a method summarize comment. it will have another method called summarize comments. And it can have parameters which you know flip between different ideas. Another subsystem another module mustn't know anything about prompts it must just understand what it wants which of course it does and then it's the job of the agent runs to convert the intent and the desire of other modules into prompts

Settled: Agent runs owns every prompt; callers state what they want done.

## Q20 — How is agent runs' interface shaped?

Recommended: Roles: Summaries, PR work, Thread work, History.

> Agreed. It should be split by roles. I really like that. yeah, that, that should be fine.

Settled: Roles.

## Q21 — Who owns the command lines the agent reports back with?

Recommended: The CLI owns them; wiring hands them to agent runs.

> Okay, that's fine. the cli can own them.

Settled: As recommended.

## Q22 — Where does 'a repo is owner/name' live?

Recommended: A Repo type in GitHub.

> repo in GitHub, I agree.

Settled: Repo in GitHub (later moved to the kernel by Q32).

## Q23 — Who owns what a thread record contains?

Recommended: Review threads owns the schema; thread records stores opaque documents.

> Agreed.

Settled: As recommended.

## Q24 — Does ReviewThreads.of shrink to (repo, pr)?

Recommended: Yes: every other fact from its owner.

> Yeah, 100%. There is no way you should be passing anything except repo PR.

Settled: (repo, pr) only.

## Q25 — How do working copies and PR windows authenticate without the GitHub token?

Recommended: GitHub hands out an environment, not a token.

> Okay, the Git environment for git fetch, that's not necessary. is it necessary? the wiring? Is that necessary for the TMAX PR windows? is there anything that runs something that would need the GH token?

> Yeah. I think the GH token is just a a holdover from a previous time, so just delete it, I think. I don't think it's necessary in either of the locations that it's currently being used.

Settled: GH_TOKEN deleted from both places and token() removed (merged as cab0e466).

## Q26 — Do fakes count toward a module's 5?

Recommended: No; fakes live only in <module>.fake.

> Oh yeah, no fakes don't count, that's fine.

Settled: As recommended.

## Q27 — Is a type exported only if a caller has to write its name?

Recommended: Yes.

> Yes, absolutely.

Settled: As recommended.

## Q28 — Does GitHub split into roles too?

Recommended: Roles provided directly by wiring.

> Yeah, actually, I, I like the roles provided. yeah, that's good.

Settled: PullRequests, Threads, Reviews, Access.

## Q29 — How do GitHub's wire words cross the boundary?

Recommended: Questions for decisions, one Side enum, GitHub's rules move home.

> Yep, agreed. questions for decisions. what is the side enum? I don't actually understand that. yeah, definitely the GitHub rules need to move home. But I'm not sure about side. I don't understand what the enum is, what it does, who set, like, you say the board sets it, review thread stores it, and GitHub posts it. That sounds like a problem. What is side?

Settled: Questions for decisions; GitHub's rules move home. Side went to Q30.

## Q30 — What does review threads call the diff side?

Recommended: Its own words, before and after; GitHub translates.

> Okay, I understand what the problem is. this actually is frustrating because it's the same as an integer. It's the same as the line number in terms of the data that it is. to be honest, do we have any domain objects that don't like like this, like this kind of enum that don't belong in a module? it would be great to have like a shared domain or a common domain file which basically has this kind of thing where nobody actually owns it because side is not owned the board has a right to own it in a sense but then GitHub needs it so that kind of has a, an ownership right so there's definitely a shared concept like an integer nobody owns the concept of an integer but everybody uses it so yeah that's what I'm thinking

Settled: Led to a shared kernel (Q31).

## Q31 — Do we add a shared kernel, and on what terms?

Recommended: Yes, with a strict admission rule.

> So yes, it should be with a strict admission rule.

Settled: As recommended.

## Q32 — What goes into the kernel at the start?

Recommended: Side, Location, Repo and Pr.

> Yeah, that sounds great. Go with all four.

Settled: All four.

## Q33 — Who owns what an event is?

Recommended: Change detection owns typed events.

> Yeah, okay. Good idea. Change detection owns typed events.

Settled: As recommended.

## Q34 — What does the inbox hand out about its queues?

Recommended: Typed entries.

> Okay, so I actually don't understand what the inbox is. Is that a module that we have? And what is its responsibilities? What does it do? What's its interface? Help me out here, because otherwise I can't answer this question.

> Yes, absolutely. It should return typed entries. because event file and its name is a massive leak. yeah, so the inbox should send facts. The wording definitely belongs to notifications, not to inbox.

Settled: Typed entries; the response table sends facts.

## Q35 — Does settings own both reading and writing the config?

Recommended: Settings owns the file.

> And also, inbox is a really bad name. can we rename it to... PR event queue manager

> Oh yeah, settings definitely owns both reading and writing. it owns the file, it hides everything from everybody else.

Settled: Settings owns config.toml. The inbox rename went to Q36.

## Q36 — The inbox's new name

Recommended: pr_event_queue.

> Yeah, PR event queue is fine.

Settled: pr_event_queue.

## Q37 — Who decides what to do about a worktree on the wrong branch?

Recommended: Working copies returns the verdict.

> So there's a bit of a difficult one let me see if I understand the problem correctly so the worktree ends up on the wrong branch and somebody detects the issue that would be working copies now the question is who decides what happens is it up to those who are consuming working copies that decide what to do or somewhere else and currently we have PR manager that applies some grace period and the watcher also does a apply some grace period yeah so now just to quickly check the watcher and the PR manager run in separate processes so I don't know exactly like I guess from a theoretical point of view we could still have working copies decide because it's one piece of code that's running in two different places but it's the same code so it'll give the same response But now, working copies deciding, what does that mean? What do the watcher and the PR manager do with that decision? Like, how do they even get the fact that there is a decision? Help me out here.

> Okay, so yes, both the watcher and the PR manager should ask working copies for the verdict, which it then responds with, and both the manager and the watcher then decide what, or they do what they need to do based on the decision that the working copies has decided. So, yes.

Settled: Working copies returns hold or hand off; the watcher and manager act on it.

## Q38 — Who remembers where a thread's worktree is?

Recommended: Working copies derives it; base_sha stays as the adopted marker.

> Itchy, yeah, working copies derives it. But also, can you double check that the stored field being dropped works across a restart? Because that's what I'm, that's I think why it's written down is because if something restarts, then you could end up with a problem because it's not always immediately apparent what the work trees, what work trees belong to which threads and which work trees belong to which PR and all of that kind of stuff. Can you double check that we're not going to lose anything if we go with this thing and then restarts happen at weird times?

> Yep, that's good.

Settled: Derived path and branch; the record keeps base_sha as the adopted marker.

## Q39 — How do git failures and a bad sha reach the CLI?

Recommended: Through review threads' refusal.

> Yeah, I agree.

Settled: As recommended.

## Q40 — Who owns starting, stopping and finding PR managers?

Recommended: PR windows owns the manager process's whole life.

> Oh yeah, the PR window is definitely owned the manager's process the whole life. The CLI can just call that method. On the manager on the PR window or the manager whatever but yeah no no no. this is definitely owned by PR windows

Settled: As recommended.

## Q41 — Five small PR windows leaks (a–e)

Recommended: All five as proposed.

> Go for it. That seems good.

Settled: All five.

## Q42 — Where does 'tear this PR down' live?

Recommended: One teardown in the watcher, with a reason.

> Yep, I like one teardown in the watcher with a reason.

Settled: As recommended.

## Q43 — How do dismissals cross the boundary?

Recommended: Separate verbs, questions, settings owns the rule.

> Yep. Perfect.

Settled: As recommended.

## Q44 — Who reads the run history?

Recommended: Agent runs owns the ledger; the CLI only shows it.

> Yep, exactly.

Settled: As recommended.

## Q45 — Who archives a module's state when the repo switches?

Recommended: Each module archives its own.

> start asking me maybe like three questions at a time

> Yeah, I like the idea of each module archiving its own but I think that archive folder shouldn't go in by wiring that archive folder should go in to the archive other repos method and then the switch repo call passes that path in because the modules that can archive are modules that already understand the file system and the fact that they're storing files somewhere so the fact that they receive a path actually makes sense.

Settled: Each module archives its own; switch-repo passes the archive folder in.

## Q46 — Who writes the watcher's health line?

Recommended: The watcher reports data; the CLI words it.

> agreed for Q46. That's great. Watcher reports data and the CLI words it.

Settled: As recommended.

## Q47 — Who knows the log file names?

Recommended: Settings owns the log layout.

> yeah, I agree. Settings are in the, are in the log layout, and the CLI would ask for that.

Settled: As recommended.

## Q48 — Who works out which run produced a proposal?

Recommended: The conversation answers it; the board names it.

> everything that you said sounds great. I like your suggestions.

Settled: As recommended.

## Q49 — Where does the board preview live?

Recommended: Its own dev entry point outside board_api.

> (answered with Q48)

Settled: As recommended.

## Q50 — Does thread records' per-thread inbox get renamed?

Recommended: Yes, to pending decisions.

> (answered with Q48)

Settled: As recommended.

## Q51 — Does anything still get Settings whole?

Recommended: Settings hands out a child-process environment.

> Yep, I would agree with all three of what you said.

Settled: As recommended.

## Q52 — How does change detection's Facts cross?

Recommended: A read model with questions for decisions.

> (answered with Q51)

Settled: As recommended.

## Q53 — Who creates a module's folders?

Recommended: Each module creates its own.

> (answered with Q51)

Settled: As recommended.

## Q54 — How does thread activity travel through the event queue?

Recommended: Review threads' opaque value, carried by its own queue verb.

> I don't think it's necessary for the review threads. I don't think it's necessary for it to be an opaque value. so you don't need to go through the encode decode fiasco. just make it something that is owned by the right place and passed in the right places, not just a dict, but there's no need for it to be opaque.

Settled: A typed value owned by review threads, not opaque, passed through the queue.

## Q55 — The atomic file write written in several modules

Recommended: Keep the copies.

> Q55, that's fine.

Settled: Copies stay.

## Q56 — Fakes and the tests that reach inside other modules

Recommended: Every module ships a fake with contract tests; tests go through interfaces only.

> Yep, every module ships a fake with contract tests. Yes, and the tests go through the interfaces only. Absolutely. Any test that is written that sets up a fake but that uses the internals to set up a specific state and then tests that state needs to be transformed into an a test that goes through the interface. If you can't set up the same state then well that means that the test was testing something impossible anyway because nobody else does anything except going through the the interface so yeah that's good

Settled: As recommended; unreachable states are not tested.

## Q57 — ThreadActivity makes review threads 11

Recommended: Drop Review if the projection can do without naming it.

> Yep, that all sounds good.

Settled: As recommended.

## Q58 — Notifications' item types

Recommended: Methods split into domain roles.

> (answered with Q57)

Settled: As recommended.

## Q59 — How do we record all this?

Recommended: Update the module-map spec, then republish the artifact.

> yep, spec then artifact, absolutely.

Settled: Spec, then artifact.
