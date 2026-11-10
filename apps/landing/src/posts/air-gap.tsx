import { PostByline } from '../components/blog/post-context';
import { Icon } from '../components/icon';
import { SectionLink } from '../components/section-link';
import { UnpluggedBoxArt } from '../components/post-art';

export function AirGapBody() {
  return (
    <>
      <p className="eyebrow">NuFi Box · How it works</p>
      <h1>We unplugged the internet, and the box kept answering</h1>
      <p className="standfirst">
        Some sites can't have internet at all — a secure facility, a factory floor, a government network. We built the
        box so you can carry the whole thing in on a USB stick, load it, pull the cable, and still ask your documents
        questions.
      </p>
      <PostByline />

      <p>
        The hardest version of "private" we design for is the site that takes your phone at the door. No phone, no
        guest wifi, no cable to the outside. If the AI can't live entirely inside that room, it doesn't get in. That
        rules out most of what gets sold as "private AI," because most of it still needs the internet somewhere — to
        install, to pull a model, to renew a certificate, or to run the little service that lets a laptop find the box
        from home.
      </p>
      <p>
        For a long time ours did too, in places we hadn't noticed. "Private" and "offline" turn out to be different
        promises, and when a customer whose rules forbid any outbound connection asked us to make good on the second
        one, we had to go find every spot where the box quietly reached out and close it.
      </p>

      <figure className="post-fig">
        <UnpluggedBoxArt />
        <figcaption>
          Pull the cable and the box keeps working: the model, the index and the private network are all on the box.
        </figcaption>
      </figure>

      <p>Three things were reaching out, and none of them announced it.</p>
      <p>
        <strong>The software and the model.</strong> A fresh box pulls its containers and its model from a registry on
        the internet. An air-gapped site has no registry to reach, so we pack the whole thing into one file instead —
        around seventeen images: the chat, the index, the model, the private network, all of it. You carry that file in,
        run <code>docker load</code>, and install with the pull step turned off.
      </p>
      <p>
        We shipped that bundle wrong more than once, and it taught us how unforgiving air-gap is. One build left out the
        container that runs the private network; another forgot the coordinator's own database. Both times the box came
        up looking perfectly healthy — and then the first laptop that tried to join would hang forever, because the one
        piece it needed had quietly tried to pull from a registry that wasn't there. A test can be green on a machine
        with wifi and still be wrong here. Air-gap has no "almost": either every piece is in the box, or a laptop waits
        on a download that will never finish.
      </p>
      <p>
        <strong>The certificate.</strong> A box normally gets its HTTPS certificate from a public authority, which means
        talking to the internet to get it and again to renew it. Offline that's off the table, so the box runs its own
        small certificate authority and signs for itself. The browsers on your network are told to trust that one
        authority, and nothing has to phone out to stay valid.
      </p>
      <p>
        <strong>The way people reach it from home.</strong> Letting a laptop find the box from outside the office needs
        a coordination server, and ours used to run on a rented VPS. For a site that forbids any outside dependency, a
        server we operate somewhere else is exactly the thing they can't allow — our cloud is still someone's cloud. So
        we moved it onto the box. The box now runs that coordinator itself, on its own network. There's no server of
        ours in the loop any more; the only thing anyone has to trust is the box in the room.
      </p>

      <div className="pull">Air-gap doesn't grade on a curve. Either every piece is on the box, or the box is a brick.</div>

      <p>
        Installing offline ends up looking a lot like installing online, minus the waiting: you answer a handful of
        questions, the box comes up, and it prints a URL. The difference is that nothing in those few minutes reaches
        past the machine in front of you. And the test we actually trust is the dullest one we have — pull the cable,
        reboot the box, and watch a laptop join its network, open the chat, and get an answer with its source, all with
        no route to the outside. When that run is green, privacy isn't a claim we're asking you to believe. There's no
        wire for anything to leave on.
      </p>
      <p>
        We'd rather say plainly where offline costs you. Updates arrive the way the install did: a file somebody carries
        in, not a button you press. The model is whatever you loaded, so making it smarter means bringing a newer
        bundle. And "air-gapped" describes the network, not the room — a person with access can still walk a file out on
        the same USB stick that brought the box in. What the box takes away is the quiet online path, the one that
        leaves no fingerprints and that nobody is watching.
      </p>
      <p>
        Most "AI you can run yourself" still assumes a healthy internet connection somewhere in the setup. Some of our
        customers don't have one, and aren't allowed to. So the box is built not to need it: carry it in, load it,
        unplug, and ask.
      </p>

      <div className="cta-box">
        <h2>Need AI on a network with no way out?</h2>
        <p>Tell us about the site — air-gapped, classified, offline by policy. We'll show you a box that runs there.</p>
        <SectionLink id="contact" className="btn btn--primary">
          Talk to us <Icon name="arrow" />
        </SectionLink>
      </div>
    </>
  );
}
