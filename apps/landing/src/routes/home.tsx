import { Link } from '@tanstack/react-router';
import { Icon } from '../components/icon';
import { BoxFrame } from '../components/box-frame';
import { SectionLink } from '../components/section-link';
import { DOCS_URL, EMAIL, MAILTO } from '../content';

export function Home() {
  return (
    <main>
      {/* Hero */}
      <section className="hero">
        <div className="shell hero__in">
          <div className="hero__copy">
            <p className="eyebrow">Private AI appliance</p>
            <h1>
              Private AI for teams that <span className="hl">can't</span> send data to the cloud.
            </h1>
            <p className="hero__sub">
              NuFi Box is a small on-premise appliance that runs the whole AI stack on your own hardware — a private
              chat that answers from your documents, on your GPU, on your network. Nothing leaves the box.
            </p>
            <div className="hero__cta">
              <SectionLink id="contact" className="btn btn--primary btn--lg">
                Talk to us <Icon name="arrow" />
              </SectionLink>
              <a className="btn btn--onnavy btn--lg" href={DOCS_URL} target="_blank" rel="noopener">
                <Icon name="book" /> Read the docs
              </a>
            </div>
            <p className="hero__assure">
              <Icon name="lock" /> On your hardware · On your network · No third-party API
            </p>
          </div>
          <div className="hero__media">
            <BoxFrame tag="on your box" tagIcon="lock">
              <img
                src="/shots/hero.png"
                alt="The box answers a security-policy question from the company's own handbook, with a citation"
                width={2880}
                height={2000}
              />
            </BoxFrame>
          </div>
        </div>
      </section>

      {/* Trust strip */}
      <section className="trust">
        <div className="shell trust__in">
          <span className="trust__lead">
            <Icon name="shield" /> Your data stays in the building
          </span>
          <div className="trust__tags">
            <span>Legal</span>
            <span>HR</span>
            <span>Finance</span>
            <span>Support</span>
            <span>Regulated industries</span>
            <span>Government</span>
          </div>
        </div>
      </section>

      {/* How it works */}
      <section className="section" id="how">
        <div className="shell">
          <div className="sec-head">
            <p className="eyebrow">How it works</p>
            <h2>From a shared folder to answers, in three steps</h2>
            <p>No data pipeline to build and nothing to send away. You add documents; the box does the rest.</p>
          </div>
          <div className="steps">
            <div className="step">
              <span className="step__n" />
              <h3>Drop your documents in</h3>
              <p>Create a department (HR, legal, finance) and add its files to the box's drive from the owner console.</p>
              <span className="step__flow">
                <Icon name="chev" />
              </span>
            </div>
            <div className="step">
              <span className="step__n" />
              <h3>The box indexes &amp; runs locally</h3>
              <p>Documents are embedded and the model runs on the box's own GPU. No upload, no third-party API call.</p>
              <span className="step__flow">
                <Icon name="chev" />
              </span>
            </div>
            <div className="step">
              <span className="step__n" />
              <h3>Your team asks — with citations</h3>
              <p>From anywhere, over a private encrypted mesh. Every answer shows the source document it came from.</p>
            </div>
          </div>
        </div>
      </section>

      {/* Features */}
      <section className="section section--tint" id="features">
        <div className="shell">
          <div className="sec-head">
            <p className="eyebrow">What's in the box</p>
            <h2>A full private AI stack, on hardware you own</h2>
            <p>
              Everything a cloud AI gives a team — chat, document search, assistants — without the documents ever
              leaving your network.
            </p>
          </div>
          <div className="feat">
            <div className="card">
              <div className="card__ico">
                <Icon name="lock" />
              </div>
              <h3>Nothing leaves the box</h3>
              <p>Documents, index and model all live on the appliance. It runs air-gapped if you want it to.</p>
            </div>
            <div className="card">
              <div className="card__ico">
                <Icon name="cite" />
              </div>
              <h3>Cited answers</h3>
              <p>
                Every reply is grounded in your files and shows a "Searched your files" source — not a guess from
                training data.
              </p>
            </div>
            <div className="card">
              <div className="card__ico">
                <Icon name="mesh" />
              </div>
              <h3>Private encrypted mesh</h3>
              <p>Team members reach the box from home or the road over an encrypted mesh. The documents still never leave it.</p>
            </div>
            <div className="card">
              <div className="card__ico">
                <Icon name="folder" />
              </div>
              <h3>Department workspaces</h3>
              <p>HR, legal, finance and support each get their own drive, team and assistant, with access set per file.</p>
            </div>
            <div className="card">
              <div className="card__ico">
                <Icon name="gpu" />
              </div>
              <h3>Runs on your GPU</h3>
              <p>Your hardware, your models, no per-token cloud bill. One box serves the whole team.</p>
            </div>
            <div className="card">
              <div className="card__ico">
                <Icon name="console" />
              </div>
              <h3>One owner console</h3>
              <p>Add files, invite members, set access and change the model from a single screen. No command line required.</p>
            </div>
          </div>
        </div>
      </section>

      {/* Showcase */}
      <section className="section">
        <div className="shell">
          <div className="sec-head">
            <p className="eyebrow">See it in action</p>
            <h2>It looks like the chat your team already knows</h2>
          </div>
          <div className="showcase">
            <div className="showcase__copy">
              <h3>Ask in plain language. Get an answer with its source.</h3>
              <p>
                A team member asks a normal question. The box searches the department's documents, answers from them,
                and links the file it used — so the answer is checkable, not just plausible.
              </p>
              <ul className="mini">
                <li>
                  <Icon name="check" /> Answers quote the actual figure from your document
                </li>
                <li>
                  <Icon name="check" /> Every reply carries a "Searched your files" citation
                </li>
                <li>
                  <Icon name="check" /> Nothing is logged on anyone else's server
                </li>
              </ul>
            </div>
            <div className="showcase__media">
              <BoxFrame tag="cited answer" tagIcon="lock">
                <img
                  src="/shots/qa.png"
                  alt="A cited answer about annual leave, pulled from the department's documents"
                  loading="lazy"
                  width={2880}
                  height={2000}
                />
              </BoxFrame>
            </div>
          </div>
          <div className="showcase showcase--flip">
            <div className="showcase__copy">
              <h3>One box, one assistant per department</h3>
              <p>
                Each department gets an assistant that reads only its drive. HR answers from the handbook; legal from
                the contracts; support from the product docs. Create a department, drop the documents in, and the team
                can ask.
              </p>
              <ul className="mini">
                <li>
                  <Icon name="check" /> Access is set per department and per file
                </li>
                <li>
                  <Icon name="check" /> New documents are indexed in the background
                </li>
                <li>
                  <Icon name="check" /> The same box serves every team
                </li>
              </ul>
            </div>
            <div className="showcase__media">
              <BoxFrame tag="departments" tagIcon="folder">
                <img
                  src="/shots/agents.png"
                  alt="Department assistants on the box, one per team"
                  loading="lazy"
                  width={2880}
                  height={1800}
                />
              </BoxFrame>
            </div>
          </div>
        </div>
      </section>

      {/* Security band */}
      <section className="sec-band section">
        <div className="shell">
          <div className="sec-grid">
            <div>
              <p className="eyebrow">Why on-premise</p>
              <h2>The documents never leave the box</h2>
              <p className="sec-band__lead">
                This is the part a legal, HR or finance team actually cares about. Built for teams that can't send data
                to the cloud — regulated finance, legal, healthcare and government.
              </p>
            </div>
            <div className="seal">
              <div className="seal__row">
                <Icon name="folder" />
                <div>
                  <b>Documents sit on the box</b>
                  <span>In the department's drive, on the appliance — not in a vendor's storage.</span>
                </div>
              </div>
              <div className="seal__row">
                <Icon name="gpu" />
                <div>
                  <b>The model reads them on your GPU</b>
                  <span>Indexing and generation both happen on the box. No prompt is sent to a third-party API.</span>
                </div>
              </div>
              <div className="seal__row">
                <Icon name="mesh" />
                <div>
                  <b>Remote access, data stays put</b>
                  <span>A team member at home reaches the box over an encrypted mesh — and the handbook still never leaves it.</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Blog teaser */}
      <section className="section" id="blog-teaser">
        <div className="shell">
          <div className="sec-head">
            <p className="eyebrow">From the blog</p>
            <h2>Use cases &amp; field notes</h2>
            <p>Real things we've run on a real box. Every screenshot is unretouched.</p>
          </div>
          <div className="posts">
            <Link
              to="/blog/hr-private-document-qa"
              className="post-card post-card--link"
              aria-label="Read: Ask your company handbook — privately, on your own box"
            >
              <div className="post-card__media">
                <img src="/blog/security.png" alt="A cited answer about the company security policy" loading="lazy" />
              </div>
              <div className="post-card__body">
                <span className="post-card__kicker">Use case · HR</span>
                <h3>Ask your company handbook — privately, on your own box</h3>
                <p>
                  We put an HR handbook on a NuFi Box and let the team ask it questions. Every answer cited the source.
                  Nothing left the building.
                </p>
                <span className="post-card__more">
                  Read the use case <Icon name="arrow" />
                </span>
              </div>
            </Link>
            <article className="post-card post-card--soon">
              <div className="post-card__media">
                <Icon name="book" size={40} className="" />
              </div>
              <div className="post-card__body">
                <span className="badge-soon">Coming soon</span>
                <h3>Legal over a stack of contracts</h3>
                <p>Point a department at your contracts and ask what each one actually commits you to.</p>
              </div>
            </article>
            <article className="post-card post-card--soon">
              <div className="post-card__media">
                <Icon name="console" size={40} className="" />
              </div>
              <div className="post-card__body">
                <span className="badge-soon">Coming soon</span>
                <h3>Support over the product docs</h3>
                <p>Answers your team can send to a customer, drawn from the manuals you already wrote.</p>
              </div>
            </article>
          </div>
        </div>
      </section>

      {/* Docs band */}
      <section className="section section--tint">
        <div className="shell">
          <div className="docs-band">
            <div>
              <h2>Everything is documented</h2>
              <p>
                Install, mesh setup, departments, the owner console — step by step, with screenshots. Set a box up
                yourself or follow along.
              </p>
            </div>
            <a className="btn btn--primary btn--lg" href={DOCS_URL} target="_blank" rel="noopener">
              <Icon name="book" /> Open the docs
            </a>
          </div>
        </div>
      </section>

      {/* Final CTA */}
      <section className="section final" id="contact">
        <div className="shell">
          <p className="eyebrow">Get a box</p>
          <h2>A private AI box for your team</h2>
          <p>
            Tell us what your team needs to keep private, and we'll help you stand up a box that runs your documents'
            AI on your own hardware.
          </p>
          <a className="btn btn--primary btn--lg" href={MAILTO}>
            Talk to us <Icon name="arrow" />
          </a>
          <p className="final__mail">
            or email <b>{EMAIL}</b>
          </p>
        </div>
      </section>
    </main>
  );
}
