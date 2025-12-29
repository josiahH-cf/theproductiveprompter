**tl;dr:** For a month, I used AI to ideate, write, and publish a new article every day, while automating as much of the workflow as possible. Eventually the entire process was automated. The biggest time sink wasn’t writing, but the human components. Overall, the experiment convinced me that high-volume, scheduled publishing is now largely automatable with the right pipeline. If you're writing by hand, you may be wasting your time.
## 🧪What's the Experiment?

For the past month, I used **AI to build, draft, and publish** a new article every day. The goal was to use AI for everything. Ideation > article writing > post creation > troubleshooting. The goal was also to automate everything I could (deploy articles in bulk, write in bulk, post in bulk, etc.) so I wouldn’t need to switch contexts. I fed topics through a **spec and template system** (shown here: [https://github.com/josiahH-cf/theproductiveprompter/tree/main/Article-Spec-Pack-v1](https://github.com/josiahH-cf/theproductiveprompter/tree/main/Article-Spec-Pack-v1)) and polished the draft with a tone document in the browser (although this became unnecessary with the final iteration of the spec pack).

In essence, I edited the spec pack every day, and then moved to a weekly cadence once I figured out how to do it. I automated the deployment of posts and scheduled them in bulk (usually on Mondays).

The tool I used to draft documents was GitHub Copilot with different model choices. In the browser, I mostly used GPT, although I did use Gemini every once in a while just to see what would happen.

The spec pack, posts, website, release pattern, meta-prompts, and any changes were all done using AI (essentially “vibe-coded”).

## The Workflow

1. Generate ideas using a web-based model
    
    1. GPT or Gemini—but these are just my preference. I always used the most recent model, but I could see another one being better (like 4.1 could probably have decent results, but it wasn’t tested).
        
2. Feed that list into the spec pack with GitHub Copilot.
    
    1. Creating the spec pack took an afternoon and was all done with Copilot as well.
        
3. Have it plan, then agentically write articles. Repeat that iteratively (different model choices produced different outcomes).
    
    1. 🏆Clear winner in writing was GPT (5.1 / 5.2) compared to Claude, Gemini, and Grok.
        
    2. 💭Copilot does modify its own requests and colors its prompts with language for developers, so the outcome could have been better with a more writing-centered tool.
        
4. Edit articles (if and only if needed, which was almost never).
    
    1. I was editing articles briefly before deployment, but then decided this could be automated too. Notice in the spec pack there is a QA check at the end, which is essentially what I was doing to edit the docs, but offloaded to the model as well.
        
5. Automate daily deployment of the articles using a JavaScript function that is pre-built into the site.
    
6. Write posts (I used GPT in the browser for this and modeled it after the same generic posts, emojis, etc.)
    
7. Bulk schedule them
    
    1. As the deployment on the website is also scheduled, I could bulk schedule the posts and just link the main website.
        
8. Profit
    

## What was my prediction?

The entire process would be automatable. There would be a ton of review of articles. People would criticize me. Writing articles would be easy, but re-writing them would take the bulk of time. People would scoff at doing this and the process.

## What I Learned

- **Main Lesson**: Automation was actually _simpler_ than I thought it would be. It took about 10 minutes a week to write and schedule posts. It took about 1 hour to bulk write 15 articles. The articles were (no shame) better than I could write and probably would have taken a lot more research to get there. Overall, writing articles—or really any writing—is very automatable and simple, and with a better spec pack to write with and more tailored models (like if I actually wanted to pay for tokens), I genuinely think the NYT could probably be automated at this point.
    
- **The pipeline worked.** A unified spec and a handful of templates turned vague ideas into coherent articles with almost no manual glue. Drafts needed human review, but even this became automated after a few cycles.
    
- **Writing was fast.** Once the brief and spec were in place, generating a complete draft took **about five minutes**. The longest part of each day was reading and fact-checking. See for yourself, though—the articles are very good (I would probably read them or at least reference them back in the early “Google things” days).
    
- **Different models, different voices.** Over the course of the month, I rotated through Gemini, Claude, and GPT. All were capable, but GPT-5.1 (and 5.2 eventually, although this was released about mid-way through the experiment) consistently produced the clearest prose and required the least editing. The others could be coaxed into quality output with tighter prompts and more polish, but any model could generally be used, provided your spec was right and tone was clear.
    

## Personal Lessons

- **Just iterate and post** - nobody really cared that this was happening. If I had a platform, that might be different, but then I’d probably have fact-checkers, etc., to help at that point too. If content generation and getting things out there is the goal, once the pipeline is made, everything else is just about the courage to hit “post” and confident sharing of articles I didn’t write completely. Moving into an 'editor' role instead of a writer role is a natural byproduct of modern tools.
    
- **Expect new models if you're doing something over 30 days** - AI model deployment is getting fast. New models produced new outputs. This was mostly good, but it did make me need to change the spec a few times.
    
- **Analyze the automation, not the articles** - Focus on getting good outputs first, then figure out how to automate it. Good outputs come from grounding the model with context, examples, and verifiable checklists rather than trusting its default voice or information. Clear direction is the hardest part. Know MY aim is the major constraint. Different models are trained on different data and for different reasons. If you nail the instructions and pipeline, the writing is the easy part.
    
    - 🤔My working theory is that with modern AI tools, “Prompt + Context = Anything a computer can do.” This is because I can have AI write scripts to write things, specs, meta-prompts, etc. Therefore:
        
        - Better context = better output
            
        - Better prompt = better output
            
        - By focusing on those 2 variables, I can...
            
            - Write code, build businesses, create an OS, automate replies to emails... Anything a computer can do.
                
        - Still just a working theory—but I have yet to find the limitation other than tokens.
            
- **Variance is a feature.** The models I tested sometimes returned two subtly different answers to the same prompt. That variance isn’t a bug. Use it to your advantage based on the use case and desired output.
    
- **Scheduling and posting were the hard parts** - With a simple automation pipeline and modern models, publishing one solid article per day takes 5 minutes. The real work is the **hour of human review** to check facts, tune tone, and ensure the piece reflects my own point of view. But even if someone can eventually automate this, the hard part becomes the courage to deploy something you didn’t really write, exposing yourself to criticism, and humility to post something imperfect. I spent more time thinking about what people might say if I did this than the AI took to write it.
    
    - My thought is that more than half of the articles are written by AI now (backed up by: [https://theconversation.com/more-than-half-of-new-articles-on-the-internet-are-being-written-by-ai-is-human-writing-headed-for-extinction-268354](https://theconversation.com/more-than-half-of-new-articles-on-the-internet-are-being-written-by-ai-is-human-writing-headed-for-extinction-268354)_)
        
        - Nobody owns that from my experience. They should. This is cool. This was fun.
## Final Thoughts

This experiment convinced me that **automated documentation and article writing are here today**. If you're a creative writing major, journalism major, or english major, you may be better off saving yourself the headache and debt and moving into another profession. The technology is mature enough that, with a clear spec, a basic pipeline, and a voice document, you can publish on a schedule with minimal effort.