import { PostByline } from '../components/blog/post-context';
import { Icon } from '../components/icon';
import { SectionLink } from '../components/section-link';
import { SealedBoxArt } from '../components/post-art';

export function SealedNetworkBody() {
  return (
    <>
      <p className="eyebrow">NuFi Box · How it works</p>
      <h1>The box has no road to the internet</h1>
      <p className="standfirst">
        "Private AI" has turned into a checkbox. Here's the version we can show you, not just promise: on a sealed NuFi
        Box, your documents have no route to the internet to take. It isn't a policy we swear to keep. It's a road that
        was never built.
      </p>
      <PostByline />

      <p>
        Every vendor sells "private" now. Run the model in your own cloud tenant, keep the logs in-region, sign a
        data-processing agreement, and it earns the label. That's genuinely better than pasting your contracts into a
        public chatbot. It's also still a promise: your data sits somewhere you don't control, handled by a company
        you're trusting to behave. For a lot of teams that trade is fine. The teams that call us are the ones it isn't
        fine for — the ones whose documents can't be on someone else's machine at all.
      </p>
      <p>
        So on a NuFi Box we stopped making the promise and changed the wiring. The box runs the whole stack on one
        machine: the chat, the document index, the model, the GPU. Turn on its sealed mode and the box's network is
        marked internal. There's no route from it to the open internet — not a firewall rule we keep patched, not a
        proxy the app is trusted to use. The road isn't there. A packet aimed at the outside has nowhere to go.
      </p>
      <p>
        Concretely, the box's network has no gateway to the outside at all. The single door that could reach out is a
        small proxy that forwards only to addresses you've put on a list — and if you leave the list empty, there's no
        door. The app doesn't have to be trustworthy. It has nowhere to misbehave to.
      </p>

      <figure className="post-fig">
        <SealedBoxArt />
        <figcaption>
          The box's network is sealed. Published ports still let the office and the mesh reach in; nothing routes out.
        </figcaption>
      </figure>

      <p>
        We like that it fails in the right direction. Software reaches out more than people think — a library checking
        for an update, a model runtime pinging a telemetry endpoint, a font loading from some CDN. On a normal server
        those calls succeed and nobody notices. On a sealed box they meet a network with no exit and quietly fail, and
        the box carries on. You don't have to hunt down and forbid each one; there's no road for any of them to take.
        You don't audit good behavior. You remove the option.
      </p>
      <p>
        A sealed box still has to be useful, so it isn't a brick. The office opens the chat and a laptop joins over the
        mesh exactly as before: inbound and outbound are separate doors, and we only shut the one your data would leave
        by. Someone working from home still reaches the box over an encrypted mesh, and the handbook still never leaves
        it — the mesh carries the question and the answer, not the document. If you do want something allowed out, you
        name it: a model endpoint you host, a mail relay, one address. For the strict case, the default we ship is
        nothing at all.
      </p>

      <p>Sealing the way out is the loud part. The quiet parts decide as much:</p>
      <ul>
        <li>The documents live on the box's own drive, not a vendor's bucket.</li>
        <li>
          The model reads them on the box's own GPU. No prompt goes to a third-party API, because there's no third party
          to send it to.
        </li>
        <li>Nothing lands in anyone else's logs, because there's no one else.</li>
      </ul>

      <p>
        We'd rather tell you where the line is than oversell it. A sealed network stops data from leaving on its own. It
        won't stop a person with access from copying a file to a USB stick, and it won't make the model wiser than the
        documents you fed it. "Nothing leaves the box" is a statement about the wire; your people and your policy are
        still yours to run. What the box takes off your plate is the one risk you can't fix by trusting everyone in the
        building: the quiet outbound connection you'd never have seen.
      </p>

      <div className="pull">
        Most private AI asks you to trust a promise. We'd rather hand you a box where the promise is the plumbing.
      </div>

      <p>Point it at the documents you can't put anywhere else, and ask.</p>

      <div className="cta-box">
        <h2>Want to see a sealed box?</h2>
        <p>Tell us what your team needs to keep off the internet. We'll show you a box that keeps it there.</p>
        <SectionLink id="contact" className="btn btn--primary">
          Talk to us <Icon name="arrow" />
        </SectionLink>
      </div>
    </>
  );
}
