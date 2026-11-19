import base64
import json
import logging
from datetime import date, datetime
from io import BytesIO
from typing import Iterable
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db.models import Count, Prefetch, Q
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import cache_control
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_POST
from web3 import Web3

from .models import UserProfile, candidate, elections, votes

try:
    import numpy as np
except ImportError:  # pragma: no cover - handled gracefully in runtime
    np = None

try:
    import face_recognition
except ImportError:  # pragma: no cover - handled gracefully in runtime
    face_recognition = None

logger = logging.getLogger(__name__)


class FaceRecognitionUnavailable(Exception):
    """Raised when face recognition requirements are not met."""


def _require_face_recognition() -> None:
    if face_recognition is None or np is None:
        raise FaceRecognitionUnavailable(
            "Facial recognition libraries are not installed on the server."
        )


def _decode_data_url(data_url: str) -> bytes:
    if not data_url:
        raise ValueError("missing_face_data")
    try:
        header, encoded = data_url.split(",", 1)
    except ValueError:
        encoded = data_url
    return base64.b64decode(encoded)


def _compute_face_encoding(image_bytes: bytes) -> Iterable[float]:
    _require_face_recognition()
    image = face_recognition.load_image_file(BytesIO(image_bytes))
    encodings = face_recognition.face_encodings(image)
    if not encodings:
        raise ValueError("no_face_detected")
    return encodings[0]


def _serialise_encoding(encoding: Iterable[float]) -> str:
    return json.dumps(list(encoding))


def _deserialise_encoding(payload: str):
    _require_face_recognition()
    if not payload:
        raise ValueError("missing_stored_encoding")
    return np.array(json.loads(payload), dtype=np.float32)


def _match_face(stored_encoding: str, fresh_encoding: Iterable[float]) -> float:
    stored = _deserialise_encoding(stored_encoding)
    fresh = np.array(fresh_encoding, dtype=np.float32)
    return float(np.linalg.norm(stored - fresh))


def _calculate_age(dob: date) -> int:
    today = date.today()
    years = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
    return years


# Create your views here.
def home(request):
    return render(request, 'home.html')


def landingpage(request):
    return render(request, 'landingpage.html')


def signup(request):
    if not request.user.is_authenticated:
        messages.error(request, "Please sign in to access the registration form.")
        return redirect("signin")

    if not request.user.is_superuser or request.user.username.lower() != "user":
        messages.error(request, "You do not have permission to register voters.")
        return redirect("landingpage")

    if request.method == "POST":
        username = request.POST.get('username', '').strip()
        full_name = request.POST.get('full_name', '').strip()
        email = request.POST.get('email', '').strip()
        pass1 = request.POST.get('pass1', '')
        pass2 = request.POST.get('pass2', '')
        dob_raw = request.POST.get('date_of_birth', '').strip()
        face_snapshot = request.POST.get('face_snapshot', '').strip()

        if User.objects.filter(username=username).exists():
            messages.info(request, 'Username already exists, choose a new one!')
            return redirect('signup')

        if len(full_name.split()) < 2:
            messages.error(request, "Please enter the voter's full name.")
            return redirect('signup')

        if len(pass1) < 8:
            messages.error(request, "Password must be at least 8 characters long.")
            return redirect('signup')

        if pass1 != pass2:
            messages.info(request, 'Password does not match!')
            return redirect('signup')

        try:
            dob = datetime.strptime(dob_raw, "%Y-%m-%d").date()
        except ValueError:
            messages.error(request, "Please provide a valid date of birth.")
            return redirect('signup')

        if _calculate_age(dob) < 18:
            messages.error(request, "Only users who are 18 years or older can be registered.")
            return redirect('signup')

        if not face_snapshot:
            messages.error(request, "Facial capture is required before signing up.")
            return redirect('signup')

        try:
            face_bytes = _decode_data_url(face_snapshot)
            face_encoding = _compute_face_encoding(face_bytes)
        except FaceRecognitionUnavailable as exc:
            messages.error(request, str(exc))
            return redirect('signup')
        except ValueError as exc:
            error_code = str(exc)
            if error_code == "no_face_detected":
                messages.error(request, "We could not detect a face in the captured image. Please try again.")
            else:
                messages.error(request, "Captured face data is invalid. Please retry.")
            return redirect('signup')
        except Exception:  # pragma: no cover - unexpected errors
            logger.exception("Failed to process facial data during signup.")
            messages.error(request, "Facial recognition failed. Please try again.")
            return redirect('signup')

        myuser = User.objects.create_user(username, email, pass1)
        myuser.first_name = full_name
        myuser.save()

        UserProfile.objects.create(
            user=myuser,
            date_of_birth=dob,
            face_encoding=_serialise_encoding(face_encoding),
            face_snapshot=face_snapshot,
        )
        messages.success(request, "Account successfully created, the user can now sign in.")
        return redirect('signin')

    return render(request,'signup.html')


def signin(request):
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        pass1 = request.POST.get('pass1', '')
        face_snapshot = request.POST.get('face_snapshot', '').strip()
        if len(pass1) < 8:
            messages.error(request,"Password must be at least 8 characters long.")
            return render(request, 'signin.html')
        if not face_snapshot:
            messages.error(request, "Facial verification is required to sign in.")
            return render(request, 'signin.html')

        user = authenticate(username=username, password=pass1)
        if user is not None:
            try:
                profile = user.profile
            except UserProfile.DoesNotExist:
                messages.error(request, "No facial data is registered for this account. Please contact support.")
                return render(request, 'signin.html')

            try:
                face_bytes = _decode_data_url(face_snapshot)
                face_encoding = _compute_face_encoding(face_bytes)
                distance = _match_face(profile.face_encoding, face_encoding)
            except FaceRecognitionUnavailable as exc:
                messages.error(request, str(exc))
                return render(request, 'signin.html')
            except ValueError as exc:
                if str(exc) == "no_face_detected":
                    messages.error(request, "We could not detect a face in the captured image. Please try again.")
                else:
                    messages.error(request, "Facial verification data is invalid. Please retry.")
                return render(request, 'signin.html')
            except Exception:  # pragma: no cover - unexpected errors
                logger.exception("Failed to process facial data during signin.")
                messages.error(request, "Facial recognition failed. Please try again.")
                return render(request, 'signin.html')

            match_threshold = getattr(settings, "FACE_MATCH_THRESHOLD", 0.45)
            if distance > match_threshold:
                messages.error(request, "Facial verification failed. Please try again.")
                return render(request, 'signin.html')

            login(request, user)
            return redirect('landingpage') 
        else:
            messages.error(request, "Incorrect Username or Password, try again!")
    return render(request, 'signin.html')


def signout(request):
    logout(request)
    return redirect('signin')


# ── Ganache (keep your config)
w3 = Web3(Web3.HTTPProvider('http://localhost:7545'))
VOTING_CONTRACT_ADDRESS = '0xd8b934580fcE35a11B58C6D73aDeE468a2833fa8'
VOTING_CONTRACT_ABI =[
	{
		"inputs": [],
		"stateMutability": "nonpayable",
		"type": "constructor"
	},
	{
		"inputs": [
			{
				"internalType": "uint256",
				"name": "_candidateId",
				"type": "uint256"
			},
			{
				"internalType": "string",
				"name": "_electionName",
				"type": "string"
			},
			{
				"internalType": "string",
				"name": "_userName",
				"type": "string"
			},
			{
				"internalType": "string",
				"name": "_candidateName",
				"type": "string"
			}
		],
		"name": "vote",
		"outputs": [],
		"stateMutability": "nonpayable",
		"type": "function"
	},
	{
		"inputs": [
			{
				"internalType": "uint256",
				"name": "",
				"type": "uint256"
			}
		],
		"name": "candidates",
		"outputs": [
			{
				"internalType": "uint256",
				"name": "id",
				"type": "uint256"
			},
			{
				"internalType": "string",
				"name": "name",
				"type": "string"
			},
			{
				"internalType": "uint256",
				"name": "votes",
				"type": "uint256"
			}
		],
		"stateMutability": "view",
		"type": "function"
	},
	{
		"inputs": [],
		"name": "candidatesCount",
		"outputs": [
			{
				"internalType": "uint256",
				"name": "",
				"type": "uint256"
			}
		],
		"stateMutability": "view",
		"type": "function"
	},
	{
		"inputs": [
			{
				"internalType": "uint256",
				"name": "",
				"type": "uint256"
			},
			{
				"internalType": "address",
				"name": "",
				"type": "address"
			}
		],
		"name": "hasVotedForCandidate",
		"outputs": [
			{
				"internalType": "bool",
				"name": "",
				"type": "bool"
			}
		],
		"stateMutability": "view",
		"type": "function"
	},
	{
		"inputs": [
			{
				"internalType": "uint256",
				"name": "",
				"type": "uint256"
			},
			{
				"internalType": "address",
				"name": "",
				"type": "address"
			}
		],
		"name": "hasVotedInElection",
		"outputs": [
			{
				"internalType": "bool",
				"name": "",
				"type": "bool"
			}
		],
		"stateMutability": "view",
		"type": "function"
	},
	{
		"inputs": [],
		"name": "totalVotes",
		"outputs": [
			{
				"internalType": "uint256",
				"name": "",
				"type": "uint256"
			}
		],
		"stateMutability": "view",
		"type": "function"
	},
	{
		"inputs": [
			{
				"internalType": "uint256",
				"name": "",
				"type": "uint256"
			},
			{
				"internalType": "address",
				"name": "",
				"type": "address"
			}
		],
		"name": "votes",
		"outputs": [
			{
				"internalType": "uint256",
				"name": "candidateId",
				"type": "uint256"
			},
			{
				"internalType": "string",
				"name": "electionName",
				"type": "string"
			},
			{
				"internalType": "string",
				"name": "candidateName",
				"type": "string"
			},
			{
				"internalType": "string",
				"name": "userName",
				"type": "string"
			}
		],
		"stateMutability": "view",
		"type": "function"
	},
	{
		"inputs": [
			{
				"internalType": "address",
				"name": "",
				"type": "address"
			}
		],
		"name": "votesByUser",
		"outputs": [
			{
				"internalType": "uint256",
				"name": "",
				"type": "uint256"
			}
		],
		"stateMutability": "view",
		"type": "function"
	}
]
def electionlist(request):
    qs = (
        elections.objects
        .prefetch_related('candidates')
        .annotate(num_candidates=Count('candidates'))
        .filter(Q(ends_at__isnull=True) | Q(ends_at__gt=timezone.now()))
    )
    # Hide elections the user already voted in (current UX)
    if request.user.is_authenticated:
        voted_ids = votes.objects.filter(user=request.user).values_list('election_id', flat=True)
        qs = qs.exclude(id__in=voted_ids)
    return render(request, 'electionlist.html', {'elections': qs})

@ensure_csrf_cookie  # ensures we have a CSRF cookie for JS fetch
def electiondetail(request, election_id: int):
    el = get_object_or_404(
        elections.objects.prefetch_related(
            Prefetch('candidates', queryset=candidate.objects.order_by('candidatename'))
        ),
        pk=election_id
    )
    return render(request, 'electiondetail.html', {'election': el, 'candidates': el.candidates.all()})

@require_POST
@login_required
def votecandidate(request):
    """Accepts form POST or AJAX (fetch). On AJAX, returns JSON; else redirects."""
    cand_id = request.POST.get('pid') or request.POST.get('candidate_id')
    cand = get_object_or_404(candidate, id=cand_id)
    elec = cand.elections

    # Block double-voting (pairs with DB UniqueConstraint if you added it)
    if votes.objects.filter(election=elec, user=request.user).exists():
        if request.headers.get('x-requested-with') == 'XMLHttpRequest' or 'application/json' in request.headers.get('Accept',''):
            return JsonResponse({"ok": False, "reason": "already_voted", "election": elec.name}, status=409)
        messages.warning(request, f"You have already voted in '{elec.name}'.")
        return redirect('electionlist')

    # Local tally + DB row
    cand.vote = (cand.vote or 0) + 1
    cand.save(update_fields=['vote'])
    votes.objects.create(election=elec, candidate=cand, user=request.user)

    # Blockchain write (kept as-is; order matches Solidity signature)
    if w3.is_connected():
        contract = w3.eth.contract(address=VOTING_CONTRACT_ADDRESS, abi=VOTING_CONTRACT_ABI)
        tx_hash = contract.functions.vote(
            cand.id,
            elec.name,
            request.user.get_username(),
            cand.candidatename
        ).transact({'from': w3.eth.accounts[0]})
        w3.eth.wait_for_transaction_receipt(tx_hash)

    if request.headers.get('x-requested-with') == 'XMLHttpRequest' or 'application/json' in request.headers.get('Accept',''):
        return JsonResponse({"ok": True, "candidate": cand.candidatename, "election": elec.name})

    messages.success(request, f"Your vote for '{cand.candidatename}' in '{elec.name}' was successful!")
    return redirect('electionlist')



# ---- internal helpers -------------------------------------------------
from django.contrib.auth import get_user_model
from django.db.models import Count

def _aggregate_results(elec) -> dict:
    """
    Return a dict with totals + per-candidate results for an election.
    Uses total active users as 'registered' if no specific voter field exists.
    """
    User = get_user_model()

    # votes per candidate
    tally = (
        votes.objects
        .filter(election=elec)
        .values("candidate_id")
        .annotate(v=Count("id"))
    )
    tally_map = {row["candidate_id"]: row["v"] for row in tally}

 
    cand_qs = elec.candidates.all().order_by("candidatename")


    total_votes = sum(tally_map.values())

 
    registered = User.objects.filter(is_active=True).count()


    turnout_percent = round((total_votes / max(registered, 1)) * 100, 1)

   
    rows = []
    for c in cand_qs:
        v = tally_map.get(c.id, 0)
        pct = (v / total_votes * 100.0) if total_votes else 0.0
        rows.append({
            "candidate": c,
            "votes": v,
            "percent": round(pct, 2),
            "is_leader": False,
            "is_tied": False,
        })

    # determine leader(s)
    if rows:
        max_v = max(r["votes"] for r in rows)
        leaders = [r for r in rows if r["votes"] == max_v and max_v > 0]
        for r in rows:
            r["is_leader"] = r in leaders
            r["is_tied"] = (len(leaders) > 1) and (r in leaders)
        leader_row = leaders[0] if leaders else None
    else:
        leader_row = None

    # sort by votes desc, then name
    rows.sort(key=lambda r: (-r["votes"], r["candidate"].candidatename.lower()))

    return {
        "totals": {
            "total_votes": total_votes,
            "registered": registered,
            "turnout_percent": turnout_percent,
        },
        "results": rows,
        "leader": leader_row,
    }
# ---- HTML page --------------------------------------------------------
from django.urls import reverse

@login_required

def results_page(request, election_id: int):
    # Fetch election + candidates efficiently
    elec = get_object_or_404(
        elections.objects.prefetch_related("candidates"),
        id=election_id,
    )

    # Aggregate tallies (your existing helper)
    data = _aggregate_results(elec)  # expects dict with keys: "totals", "results", ["leader"]

    # Build the JSON endpoint URL the right way
    results_api_url = request.build_absolute_uri(
        reverse("results_json", args=[elec.id])
    )

    # Render detail page
    return render(
        request,
        "results.html",
        {
            "election": elec,
            "totals": data["totals"],
            "results": data["results"],
            "leader": data.get("leader"),
            "results_api_url": results_api_url,
        },
    )

# ---- JSON endpoint (for polling) -------------------------------------

@login_required
@cache_control(no_cache=True, must_revalidate=True, max_age=0)
def results_json(request, election_id: int):
    elec = get_object_or_404(
        elections.objects.prefetch_related("candidates"),
        id=election_id
    )
    data = _aggregate_results(elec)

    # convert candidates to a lean JSON shape
    def skinny(row):
        c = row["candidate"]
        return {
            "id": row["id"],
            "name": c.candidatename,
            "image_url": getattr(c, "image_url", "") or "",
            "votes": row["votes"],
            "percent": float(row["percent"]),
            "is_leader": row["is_leader"],
            "is_tied": row["is_tied"],
        }

    out = {
        "election": {
            "id": elec.id,
            "name": elec.name,
            "ends_at": getattr(elec, "ends_at", None),
        },
        "totals": data["totals"],
        "results": [skinny(r) for r in data["results"]],
        "leader": (skinny(data["leader"]) if data["leader"] else None),
    }
    return JsonResponse(out, safe=False)

# vote/views.py (additions, keep your existing imports and helpers)
from django.contrib.auth.decorators import login_required
from django.db.models import Prefetch

@login_required
def results_index(request):
    # Prefetch candidates so _aggregate_results doesn't re-hit the DB per election
    qs = (
        elections.objects
        .prefetch_related(Prefetch("candidates", queryset=candidate.objects.order_by("candidatename")))
        .all()
        .order_by("-id")  # newest first; change if you like
    )

    items = []
    for elec in qs:
        data = _aggregate_results(elec)
        leader = data["leader"]
        items.append({
            "election": elec,
            "totals": data["totals"],
            "leader": leader,           # may be None
            "results": data["results"], # used to draw tiny bars
        })

    return render(request, "results_index.html", {"items": items})


# vote/views.py (optional)
from django.contrib import messages
from django.contrib.auth.views import PasswordChangeView
from django.urls import reverse_lazy
from django.contrib.auth.mixins import LoginRequiredMixin

class GPasswordChangeView(LoginRequiredMixin, PasswordChangeView):
    template_name = "changepassword.html"
    success_url = reverse_lazy("password_change_done")

    def form_valid(self, form):
        messages.success(self.request, "Password updated successfully.")
        return super().form_valid(form)