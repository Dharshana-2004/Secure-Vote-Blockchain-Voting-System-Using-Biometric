# votes/models.py
from django.conf import settings
from django.db import models
from django.utils import timezone

class elections(models.Model):
    PUBLIC = 'Public'
    INTERNAL = 'Internal'
    SCOPE_CHOICES = ((PUBLIC, 'Public'), (INTERNAL, 'Internal'))

    name = models.CharField(max_length=100)
    scope = models.CharField(max_length=8, choices=SCOPE_CHOICES, default=PUBLIC)
    ends_at = models.DateTimeField(null=True, blank=True)
    description = models.TextField(blank=True, default='')

    def __str__(self):
        return self.name

    @property
    def is_open(self):
        return self.ends_at is None or self.ends_at > timezone.now()

    @property
    def candidates_count(self):
        return self.candidates.count()


class candidate(models.Model):
    elections = models.ForeignKey(
        elections, on_delete=models.CASCADE, default=1, related_name='candidates'
    )
    candidatename = models.CharField(max_length=50, default='', blank=True)
    image = models.ImageField(upload_to='uploads/candidate/')
    vote = models.IntegerField(default=0)

    def __str__(self):
        return self.candidatename


class votes(models.Model):
    election = models.ForeignKey(elections, on_delete=models.CASCADE)
    candidate = models.ForeignKey(candidate, on_delete=models.CASCADE)
    # 🔧 point to built-in User model
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)

    def __str__(self):
        return f"{self.user.username} voted for {self.candidate} in {self.election}"

    class Meta:
        # optional but recommended: one vote per user per election
        constraints = [
            models.UniqueConstraint(
                fields=['election', 'user'], name='one_vote_per_election_per_user'
            )
        ]


class UserProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='profile',
    )
    date_of_birth = models.DateField()
    face_encoding = models.TextField()
    face_snapshot = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"{self.user.username} profile"
