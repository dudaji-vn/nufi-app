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
          <p className="eyebrow">NuFi Box · Use case</p>
          <h1>Ask your company handbook — privately, on your own box</h1>
          <p className="standfirst">
            We put an HR handbook on a NuFi Box and let the team ask it questions. Every answer cited the source
            document. Nothing left the building.
          </p>
          <p className="byline">NuFi Box · a private, on-premise AI appliance</p>

          <h2>The problem</h2>
          <p>
            Every team has documents it can't paste into a public chatbot: the employee handbook, contracts, internal
            policies, customer records. The moment a question about one of them goes to a cloud AI, the document — or
            enough of it to matter — leaves your control. For most companies, and nearly every regulated one, that's a
            non-starter.
          </p>
          <p>
            So the documents sit in a shared folder nobody reads, and <em>"just ask HR"</em> stays the only interface.
            The knowledge is there; it just isn't answerable.
          </p>

          <h2>What a NuFi Box is</h2>
          <p>
            A <strong>NuFi Box</strong> is a small on-premise appliance that runs the whole AI stack on{' '}
            <strong>your own hardware</strong>: a private chat that answers from your documents, on your GPU, on your
            network. The documents are indexed locally, the model runs locally, and the answer is generated locally.
            Nothing is sent to a third-party API.
          </p>

          <h2>The use case: an HR assistant that actually reads the handbook</h2>
          <p>
            We dropped a company handbook — working hours, annual leave, expenses, benefits, the code of conduct, the
            IT-security policy — into the box's <strong>HR department drive</strong>. The box indexed it in the
            background. Then we asked it the questions employees actually ask.
          </p>

          <p className="q">"How many days of annual leave do I get after three years?"</p>
          <figure>
            <img
              src="/blog/annual-leave.png"
              alt="The box answers the annual-leave question from the handbook, with a citation"
              loading="lazy"
            />
            <figcaption>
              Asked in plain language, answered from the handbook — <strong>20 days from the third year</strong> — with
              a "Searched your files" citation. Not a guess from the model's training: it's pulled from <em>your</em>{' '}
              document.
            </figcaption>
          </figure>

          <p className="q">"Can I work from home, and how many days a week?"</p>
          <figure>
            <img
              src="/blog/remote.png"
              alt="The box answers the remote-work question, quoting the policy"
              loading="lazy"
            />
            <figcaption>
              The remote-work policy, quoted straight from the document — up to three days a week, agreed with your
              manager.
            </figcaption>
          </figure>

          <p className="q">"What's the daily limit for meal expenses when travelling?"</p>
          <figure>
            <img
              src="/blog/expenses.png"
              alt="The box quotes the meal-expense limit from the expenses section"
              loading="lazy"
            />
            <figcaption>
              The box quotes the actual figure — <strong>$40 per day</strong> — from the expenses section, not a
              plausible-sounding number.
            </figcaption>
          </figure>

          <p className="q">"Can I copy internal documents to my personal Google Drive?"</p>
          <figure>
            <img
              src="/blog/security.png"
              alt="The box answers the security-policy question correctly from the company document"
              loading="lazy"
            />
            <figcaption>
              The one that matters most for a <em>private</em> AI: the box answers a <strong>security-policy</strong>{' '}
              question correctly, from the company's own document — without that document ever leaving the box.
            </figcaption>
          </figure>

          <h2>Why the citation matters</h2>
          <p>
            An AI that answers HR questions is useful. An AI that answers them{' '}
            <strong>and shows which part of the handbook it used</strong> is trustworthy. An employee can open the
            source; HR can see the box isn't inventing policy. The citation turns <em>"the chatbot said so"</em> into{' '}
            <em>"the handbook says so — here."</em>
          </p>

          <div className="pull">
            The box answered a question about the company's own security policy — correctly, from the company's own
            document — without that document ever touching the cloud. That is the whole point.
          </div>

          <h2>Nothing leaves the box</h2>
          <p>This is the part a legal, HR, or finance team cares about:</p>
          <ul>
            <li>
              The documents sit in the department's drive <strong>on the box</strong>.
            </li>
            <li>
              The model reads them and generates the answer <strong>on the box's GPU</strong>.
            </li>
            <li>
              A team member at home reaches the box over a <strong>private, encrypted mesh</strong> — and still, the
              handbook never leaves the box.
            </li>
          </ul>
          <p>
            No document is uploaded to a vendor. No prompt is logged on someone else's server. For a team sitting on
            sensitive documents, that's the difference between <em>"we'd love to use AI on this"</em> and{' '}
            <em>"we actually can."</em>
          </p>

          <h2>It's the same for any team</h2>
          <p>
            HR over the handbook is one example. The box treats every department the same way: <strong>legal</strong>{' '}
            over contracts, <strong>support</strong> over the product docs, <strong>finance</strong> over the SOPs.
            Create a department, drop the documents in, and the team can ask — with citations, on your own hardware.
          </p>

          <div className="cta-box">
            <h2>Want a private AI box for your team?</h2>
            <p>NuFi Box runs your documents' AI on your own hardware — nothing leaves the building.</p>
            <SectionLink id="contact" className="btn btn--primary">
              Talk to us <Icon name="arrow" />
            </SectionLink>
          </div>

          <p className="foot-note">
            Captured live on a real NuFi Box (GPU inference, department-drive RAG). The handbook shown is a synthetic
            sample; the screenshots are unretouched.
          </p>
        </article>
      </div>
    </main>
  );
}
