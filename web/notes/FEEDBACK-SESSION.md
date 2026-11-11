# Max's feedback during the ten-build session, verbatim (10 Nov 2026)

Saved so that the audit criteria can be checked against what was said, not against a summary of it.
Images that came with some messages are not reproduced.

## 1. After v04 and the chain
"Usability is really tough. I can't easily undo actions and the zones are tough to get.

The plug and socket chain is definitely the direction that I want to go in, but everything needs to be part of a chain. It's not text embedded. It's not plugs and sockets embedded in text. Everything is going to be part of the chain.

Similarly, the UI should just be a different tab.

And then just remove all of the LLM generated text and like the different states and stuff on the main uh UI. Like it's okay that uh like you need to have the least amount of text possible here. I don't want to see all of your own bullshit text.

"Dragology only measures rect, circle and line elements, so it can't see my path-drawn place chips; I'm adding an invisible rect to each chip as its hit area." Yeah, I don't think that's true. Uh if you look at their examples, I think that's just not true."

## 2. After v05
"This looks a lot better.
* It is still fundamentally not draggable. Every piece of text needs to be draggable.
* There is no linking of states between the dragging we are doing and any of the types or other objects in the world - That's a big part of why Dragable is interesting at all. Please go back and look at its examples for inspiration and incorporate that into V5.
* You don't expose all of the data for every piece. That's a big miss
* There is no way that I can change anything in the world.
* As far as I can tell, the drop down doesn't do anything.
* I would also like to see this tested on longer pieces of text."

## 3. On what dragging a word means
"Right. So dragging the that's the key design principle here. Dragging the words isn't about moving the position of the word, right? Like the position of the word stays the same. We're dragging the sorts of things the words are tagged with and what is being tagged. And then also that the second thing is probably showing how the world relates to each other, which is not visualized at all on the page right now."

## 4. After v08
"1. I don't like that the text is duplicated. I don't understand why it would be.
   1. It also makes it unclear what you're supposed to drag, like - I think the UI is saying that this is tagged as a code change, which might be correct, but I don't understand. Do I drag it to the right or down or what?
2. I like that the highlighting works now, but it reveals that I still don't think you're encoding all of the states or all of the underlying state families.
   1. Clearly functions are typed with inputs and outputs. And that's not visualized today at all. And there's no way to see. Like if I grab a string, which things take strings.
   2. When I click on the code, I don't see what the code inherits from, or it's made of, or it's sum or product types.
   3. Don't we have concepts of kinds and brands and folding and unfolding? I don't know if we need all of those, but if we're deferring them, we should say why and how.
   4. Functions also uh don't the functions and classes both have doc strings that would be useful to include somewhere. Maybe when clicked on or represent in some way and aren't those typed as well.
   5. How do I visualize the sum and product types of each of these? Right now those appear to be absent, I think.
   6. It feels like you should re-rank the things as you grab them. So anything that you can actually drag to is on one page versus having to try and scroll up and down dramatically. That's a microphone.
3. I like the actions being prominent and being the only thing to work on, but I think you're misusing some of the motifs because it's unclear what you're talking about with like, for example,
   1. What are these four question marks trying to say? Is there a way we can make the question marks carry more information, or is there another symbol we can be using? The rows seem fairly arbitrary once you get out of the text themselves.
   2. I'd also dispute that the world visualization should just be a linear plug where everything is plugged into the next one. That is not based on the data whatsoever.
4. The text spacing doesn't seem to make much sense. I don't think there's any real thought into the spacing or typography.
5. You still can't do anything with the words. You can drag them, but you can't change how wide a tag is, for example. If I drag 'rewrite' Into 'this version' Nothing happens."

## 5. On the plan
- "Uh you have to incorporate another five in the budget now. And your patches need to be substantially larger than they have been. Um all of these should go into patch ten, and then you need to do five more after that."
- "After you're done with V10, check to make sure that the grading criteria you've been using are correct versus the original specifications that were given from the other agents using and using independent sub agent to make sure you're not lying to yourself."
- "I'm gonna have another agent, your parent agent send you a note with some more data to try and incorporate as well."
- "Once you're done with uh V15, your goal is complete."

## 6. Earlier in the session (the goal, and the pasted handoffs)
- Goal: "Ten builds each better than the last. Meeting all of the criteria provided."
- The pasted records from the other agents are `REQUESTS-FEEDBACK-AND-UNDELIVERED.md` (R01 to R48) and `UI_NOTES_AND_CRITIQUE.md`, in `/Users/max/Documents/scriptt-ui-handoff-2026-11-10/` and `/Users/max/Documents/scriptt-release/web/public/`.
- Max's clarification quoted there: "I just want text that looks like Legos and it's made of types and can be organized and uses the data that's coming from the fucking thing."
