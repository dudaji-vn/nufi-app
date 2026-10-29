import { Link } from '@tanstack/react-router';
import { Icon } from '../components/icon';
import { SectionLink } from '../components/section-link';

export function BlogPost() {
  return (
    <main>
      <div className="shell post-view">
        <article className="article">
          <Link className="back" to="/blog">
            <Icon name="arrow-l" /> All posts
          </Link>
          <p className="eyebrow">NuFi Box · Field notes</p>
          <h1>We put our HR handbook on a box and let the team interrogate it</h1>
          <p className="standfirst">
            One afternoon, one handbook, one box on the office network. The team asked it the questions they'd normally
            email HR. It answered from the document, quoted the source, and never sent a word to the cloud.
          </p>
          <p className="byline">NuFi Box · field notes from the team</p>

          <p>
            Every company has a folder like this: the handbook, the contracts, the policies, the customer files. It's the
            knowledge people actually need, and it's the exact knowledge you can't paste into ChatGPT. So it sits in a
            shared drive, half of it out of date, and "just ask HR" stays the only interface anyone trusts.
          </p>
          <p>
            We wanted to see how far a private box could close that gap, so we skipped the slideware. We took a real
            handbook (working hours, leave, expenses, the code of conduct, the IT-security policy) and dropped it into
            the HR drive on a NuFi Box, then let it index. Then we asked the boring, real questions.
          </p>

          <p className="q">"How many days of annual leave do I get after three years?"</p>
          <figure>
            <img
              src="/blog/annual-leave.png"
              alt="The box answers the annual-leave question from the handbook, with a citation"
              loading="lazy"
            />
          </figure>
          <p>
            Twenty, from the third year. It didn't guess a round number that sounded right. It lifted the figure
            straight out of the handbook and showed us the line it came from. That small "Searched your files" tag
            matters more than it looks: it's the difference between an answer you forward to an employee and one you have
            to go check yourself.
          </p>

          <p className="q">"Can I work from home, and how many days a week?"</p>
          <figure>
            <img
              src="/blog/remote.png"
              alt="The box answers the remote-work question, quoting the policy"
              loading="lazy"
            />
          </figure>
          <p>Up to three, agreed with your manager. Straight from the remote-work policy, not a vibe.</p>

          <p className="q">"What's the daily limit for meal expenses when travelling?"</p>
          <figure>
            <img
              src="/blog/expenses.png"
              alt="The box quotes the meal-expense limit from the expenses section"
              loading="lazy"
            />
          </figure>
          <p>Forty dollars a day. A cloud model will happily invent a plausible number here. This one quoted ours.</p>

          <p className="q">"Can I copy internal documents to my personal Google Drive?"</p>
          <figure>
            <img
              src="/blog/security.png"
              alt="The box answers the security-policy question correctly from the company document"
              loading="lazy"
            />
          </figure>
          <p>
            No. And it got that right from the company's own security policy, without that policy ever leaving the box.
            Read that sentence again, because it's the whole reason the box exists: the most sensitive question we could
            ask got the correct answer, and the document holding it never touched the internet.
          </p>

          <div className="pull">
            An AI that answers HR questions is a party trick. The useful version shows its source, so people trust it.
          </div>

          <p>
            An employee can open the page the answer came from; HR can see the box isn't inventing policy. Citation turns
            "the chatbot said so" into "the handbook says so, here." That one change is what moves a private AI from a
            demo to something a team leaves running.
          </p>
          <p>
            The part a legal or finance team cares about is the dull part: nothing moved. The documents stayed in the
            department drive on the box. The model read them on the box's GPU. Someone working from home reached the box
            over an encrypted mesh, and the handbook still never left it. No upload, no vendor, no prompt sitting in
            anyone else's logs.
          </p>
          <p>
            HR over a handbook is just the first drive we pointed it at. Every department works the same: legal over the
            contracts, support over the product docs, finance over the SOPs. Make a department, drop the files in, ask.
            That's the box.
          </p>

          <div className="cta-box">
            <h2>Want a box like this?</h2>
            <p>Tell us what's in the shared drive nobody opens. We'll help you put it on a box of your own.</p>
            <SectionLink id="contact" className="btn btn--primary">
              Talk to us <Icon name="arrow" />
            </SectionLink>
          </div>

          <p className="foot-note">
            Captured on a real NuFi Box (GPU inference, department-drive RAG). The handbook is a synthetic sample; the
            screenshots are untouched.
          </p>
        </article>
      </div>
    </main>
  );
}
