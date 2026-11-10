import { PostByline } from '../components/blog/post-context';
import { Icon } from '../components/icon';
import { SectionLink } from '../components/section-link';
import { IndexingArt, AnsweringArt } from '../components/post-art';

export function AnsweringBody() {
  return (
    <>
      <p className="eyebrow">NuFi Box · How it works</p>
      <h1>How the box answers from your files</h1>
      <p className="standfirst">
        The most common question we get about the box isn't about privacy. It's simpler, and more honest: how does it
        actually know what's in my documents? It didn't write them, and we didn't train it on them.
      </p>
      <PostByline />

      <p>
        The short answer is that it reads them when you add them, the way a diligent new hire would, and then reads the
        relevant few again every time someone asks. No training, no magic — two steps, both of them on the box.
      </p>

      <p>
        <strong>First, it reads your documents.</strong> When you drop a file into a department's drive, the box picks
        it up on its own and breaks it into small passages, a paragraph or two at a time. Then it turns each passage
        into what you can think of as a fingerprint: a long list of numbers that captures what the passage is{' '}
        <em>about</em>, not which words it happens to use. "Twenty days of leave from the third year" and "after three
        years your allowance rises to twenty days" land in nearly the same spot, because they mean the same thing. The
        reading, the splitting and the fingerprinting all happen on the box's own GPU, and the fingerprints go into a
        private index that sits on the machine and never leaves it.
      </p>

      <figure className="post-fig post-fig--wide">
        <IndexingArt />
        <figcaption>
          Every document is split into passages and embedded on the box's GPU into a private, on-box index. Nothing is
          uploaded, and no model has answered anything yet.
        </figcaption>
      </figure>

      <p>
        At that point the box still hasn't answered a single question. It has done something quieter: made your
        documents searchable by meaning. A keyword search finds the files that contain a word. This finds the passages
        that are about what you asked, even when they don't share a single word with the question.
      </p>

      <p>
        <strong>Then it answers from what it found.</strong> When someone asks a question, the box turns the question
        into the same kind of fingerprint and uses it to pull the handful of passages that actually match — not the ones
        that share a term, the ones that share a meaning. Only then does the model get involved. It reads those few
        passages and writes the answer out of them, in plain language. It isn't recalling something it absorbed in
        training; it's reading the specific pieces of <em>your</em> document that the search just handed it, and
        answering from those.
      </p>

      <figure className="post-fig post-fig--wide">
        <AnsweringArt />
        <figcaption>
          The question finds the matching passages; the model, on the box's GPU, reads just those and writes the answer
          from them.
        </figcaption>
      </figure>

      <p>
        This is why a private box with a modest model can beat a giant cloud one on your own documents. The cloud model
        is working from everything it read on the internet a year or two ago. The box is working from the exact
        paragraph in your handbook that answers the question, pulled fresh. For questions about your company, specific
        and current beats enormous and general.
      </p>

      <p>
        <strong>And it shows which piece it used.</strong> Because the answer is built out of specific passages, the box
        can point straight at them. That's the "Searched your files" line under a reply — the actual source, one click
        away. It's a small detail that changes the whole relationship: you're not taking the model's word for anything,
        you're reading your own document with a shortcut. An employee can open the page; HR can confirm the box isn't
        inventing policy.
      </p>

      <p>
        Two things follow from how this works, and they're both features. It's only as good as what you gave it — ask
        about something that's in no document and the honest answer is "it isn't in your files," which beats a confident
        paragraph with nothing behind it. And it's only as current as your drive — change the handbook and the box
        re-reads the changed pages, so the answer changes with it. No retraining, no model to redeploy, no waiting.
      </p>

      <div className="pull">
        The intelligence is in the finding. The privacy is in the fact that none of it ever leaves the box.
      </div>

      <p>
        That's the whole mechanism, and the point is that it isn't a trick: read your documents on your own hardware,
        find the passages that match, answer from them, show the source.
      </p>

      <div className="cta-box">
        <h2>Curious what it'd find in your files?</h2>
        <p>Point a box at the drive your team never reads, and ask it something you'd normally email around.</p>
        <SectionLink id="contact" className="btn btn--primary">
          Talk to us <Icon name="arrow" />
        </SectionLink>
      </div>
    </>
  );
}
