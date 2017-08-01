from __future__ import unicode_literals

from datetime import datetime, timedelta
from functools import reduce

from django.contrib.auth.models import User
from django.core.urlresolvers import reverse
from django.db import models
from django.db.models.signals import post_save

from slugify import slugify

from popolo.models import Person, Post

from .needs_review import needs_review_fns


def merge_dicts_with_list_values(dict_a, dict_b):
    return {
        k: dict_a.get(k, []) + dict_b.get(k, [])
        for k in set(dict_a.keys()) | set(dict_b.keys())
    }


class LoggedActionQuerySet(models.QuerySet):

    def in_recent_days(self, days=5):
        return self.filter(
            created__gte=(datetime.now() - timedelta(days=days)))

    def needs_review(self):
        '''Return a dict of LoggedAction -> list of reasons should be reviewed'''
        return reduce(
            merge_dicts_with_list_values,
            [f(self) for f in needs_review_fns],
            {}
        )


class LoggedAction(models.Model):
    '''A model for logging the actions of users on the site

    We record the changes that have been made to a person in PopIt in
    that person's 'versions' field, but is not much help for queries
    like "what has John Q User been doing on the site?". The
    LoggedAction model makes that kind of query easy, however, and
    should be helpful in tracking down both bugs and the actions of
    malicious users.'''

    user = models.ForeignKey(User, blank=True, null=True)
    person = models.ForeignKey(Person, blank=True, null=True)
    action_type = models.CharField(max_length=64)
    popit_person_new_version = models.CharField(max_length=32)
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
    ip_address = models.CharField(max_length=50, blank=True, null=True)
    source = models.TextField()
    note = models.TextField(blank=True, null=True)
    post = models.ForeignKey(Post, blank=True, null=True)

    objects = LoggedActionQuerySet.as_manager()

    def __repr__(self):
        fmt = str("<LoggedAction username='{username}' action_type='{action_type}'>")
        return fmt.format(username=self.user.username, action_type=self.action_type)

    @property
    def subject_url(self):
        if self.post:
            # FIXME: Note that this won't always be correct because
            # LoggedAction objects only reference Post at the moment,
            # rather than a Post and an Election (or a PostExtraElection).
            election = self.post.extra.elections.get(current=True)
            return reverse('constituency', kwargs={
                'election': election.slug,
                'post_id': self.post.extra.slug,
                'ignored_slug': slugify(self.post.extra.short_label),
            })
        elif self.person:
            return reverse('person-view', kwargs={'person_id': self.person.id})
        return None

    @property
    def subject_html(self):
        if self.post:
            return '<a href="{url}">{text} ({post_slug})</a>'.format(
                url=self.subject_url,
                text=self.post.extra.short_label,
                post_slug=self.post.extra.slug,
            )
        elif self.person:
            return '<a href="{url}">{text} ({person_id})</a>'.format(
                url=self.subject_url,
                text=self.person.name,
                person_id=self.person.id)
        return ''


class PersonRedirect(models.Model):
    '''This represents a redirection from one person ID to another

    This is typically used to redirect from the person that is deleted
    after two people are merged'''
    old_person_id = models.IntegerField()
    new_person_id = models.IntegerField()


class UserTermsAgreement(models.Model):
    user = models.OneToOneField(User, related_name='terms_agreement')
    assigned_to_dc = models.BooleanField(default=False)


def create_user_terms_agreement(sender, instance, created, **kwargs):
    if created:
        UserTermsAgreement.objects.create(user=instance)

post_save.connect(create_user_terms_agreement, sender=User)
