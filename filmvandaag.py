import re

import requests
from lxml import html as lh


REGEXES = {
    'movie': {
        'title_year': re.compile(r'^(.*)\s\((\d{4})\)$'),
        'genres': re.compile(r'^(.*), te zien in \d+ biosco{1,2}p[en]*$'),
        'trailer': re.compile(r'^http://.*\.ytimg\.com/.*/(.*)/.*\.jpg$')
    }
}


def check_html(func):
    def wrapper(*args, **kwargs):
        if args[0]._html is None:
            return
        return func(*args, **kwargs)
    return wrapper


def get_element_name_url(element, name_xpath=None, url_xpath=None):
    (name,) = element.xpath(name_xpath or 'text()')
    (url,) = element.xpath(url_xpath or '@href')
    return name, url


def find_element_get_name_url(parent_element, xpath, name_xpath=None, url_xpath=None):
    (element,) = parent_element.xpath(xpath)
    return get_element_name_url(element, name_xpath, url_xpath)


def entities_list(html, xpath_elements, entity_class, http_session, xpath_name=None, xpath_url=None):
    entity_elements = html.xpath(xpath_elements)
    entities = []

    for e in entity_elements:
        name, url = get_element_name_url(e, xpath_name, xpath_url)
        url = FilmVandaag.base_url + url
        entity = entity_class(name, url, http_session)
        entities.append(entity)

    return entities


class FilmVandaag(object):
    base_url = 'http://www.filmvandaag.nl'

    def __init__(self):
        self._http_session = requests.Session()

    def fetch_cities(self):
        url = '{0}/filmladder'.format(FilmVandaag.base_url)
        resp = self._http_session.get(url)
        resp.encoding = 'utf-8'
        html = lh.fromstring(resp.text)

        return entities_list(
            html=html,
            xpath_elements='//ul/li/a[contains(@href, "/filmladder/stad/")]',
            entity_class=City,
            http_session=self._http_session,
        )

    def fetch_movies(self):
        url = '{0}/bioscoop'.format(FilmVandaag.base_url)
        resp = self._http_session.get(url)
        resp.encoding = 'utf-8'
        html = lh.fromstring(resp.text)

        return entities_list(
            html=html,
            xpath_elements='//a[contains(@class, "movielist-titel")]',
            entity_class=Movie,
            http_session=self._http_session,
        )


class Entity(object):
    def __init__(self, name, url, http_session):
        self.name = name
        self.url = url
        self._http_session = http_session
        self._html = None

    def __repr__(self):
        return r'<{0} `{1}`>'.format(self.__class__.__name__, self.name)

    def fetch_data(self):
        resp = self._http_session.get(self.url)
        resp.encoding = 'utf-8'
        self._html = lh.fromstring(resp.text)


class City(Entity):
    @property
    @check_html
    def cinemas(self):
        return entities_list(
            html=self._html,
            xpath_elements='//ul[contains(@class, "cols-3")]/li/a[contains(@href, "/filmladder/")]',
            entity_class=Cinema,
            http_session=self._http_session
        )

    @property
    @check_html
    def movies(self):
        return entities_list(
            html=self._html,
            xpath_elements='//select/option[position()>1]',
            entity_class=Movie,
            http_session=self._http_session
        )

    @property
    @check_html
    def showtimes(self):
        cinema_elements = self._html.xpath('//div[@class="filmladder-overzicht"]/h3/a')
        movie_showtimes_elements = self._html.xpath('//div[@class="filmladder filmladder-small"]')
        showtimes = []

        for cinema_el, movie_showtimes_el in zip(cinema_elements, movie_showtimes_elements):
            cinema_name, cinema_url = get_element_name_url(cinema_el)
            cinema = Cinema(cinema_name, cinema_url, self._http_session)
            showtime_box = 'span/table/tr'

            while True:
                movie_showtime_elements = movie_showtimes_el.xpath(showtime_box)
                if not movie_showtime_elements:
                    break

                movie_name, movie_url = find_element_get_name_url(
                    movie_showtimes_elements,
                    'span/h4/a',
                    name_xpath='span/text()'
                )
                movie = Movie(movie_name, movie_url, self._http_session)

                (movie_showtime_elements,) = movie_showtime_elements

                for datetime in movie_showtime_elements.xpath('td/time/@content'):
                    showtimes.append(Showtime(movie, cinema, datetime))
                showtime_box = 'span/' + showtime_box
        return showtimes


class Cinema(Entity):
    @property
    @check_html
    def city(self):
        name, url = find_element_get_name_url(
            self._html,
            '//a[contains(@href, "/filmladder/stad/")]'
        )
        return City(name, url, self._http_session)

    @property
    @check_html
    def address(self):
        address = self._html.xpath('//span[@itemprop="address"]/span/text()')
        return ', '.join(address)

    @property
    @check_html
    def showtimes(self):
        showtimes = []
        selector = '//div[@class="filmladder filmladder-large"]/span'
        while True:
            sts = self._html.xpath(selector + '/table/tr')
            if not sts:
                break

            name, url = find_element_get_name_url(
                self._html,
                selector + '/h4/a',
                name_xpath='span/text()'
            )
            movie = Movie(name, url, self._http_session)

            (sts,) = sts

            for dt in sts.xpath('td/time/@content'):
                showtimes.append(Showtime(movie, self, dt))

            selector += '/span'

        return showtimes


class Showtime(object):
    def __init__(self, movie, cinema, datetime):
        self.movie = movie
        self.cinema = cinema
        self.datetime = datetime

    def __repr__(self):
        return r'<{0} {1} {2} {3}>'.format(
            self.__class__.__name__,
            self.movie, self.cinema,
            self.datetime
        )


class Movie(Entity):
    title_regex = re.compile(r'^(.*)\s\(\d{4}\)$')

    @property
    def title(self):
        return Movie.title_regex.match(self.name).group(1)

    @property
    @check_html
    def country(self):
        return self._html.xpath(
            '//ul[@class="filmpagina-info-lijst"]/li/strong[text()="Jaar, land"]/..'
            '/a[position() >=2]/text()'
        )

    @property
    @check_html
    def duration(self):
        return self._html.xpath(
            'string(//ul[@class="filmpagina-info-lijst"]/li/strong[text()="Speelduur"]/..'
            '/span/text())'
        )

    @property
    @check_html
    def director(self):
        return self._html.xpath(
            'string(//ul[@class="filmpagina-info-lijst"]/li/strong[text()="Regisseur"]/..'
            '/span/a/text())'
        )

    @property
    @check_html
    def cast(self):
        return self._html.xpath(
            '//ul[@class="filmpagina-info-lijst"]/li/strong[text()="Acteurs"]/../div/a/text()'
        )

    @property
    @check_html
    def release_date(self):
        return self._html.xpath(
            'string(//ul[@class="filmpagina-info-lijst"]/li'
            '/strong[text()="Releasedatum (Nederland)"]/../div/span/@content)'
        )

    @property
    @check_html
    def imdb_url(self):
        return self._html.xpath(
            'string(//ul[@class="filmpagina-info-lijst"]/li/strong[text()="Meer informatie"]/..'
            '/a[text()="IMDb"]/@href)'
        )

    @property
    @check_html
    def synopis(self):
        return self._html.xpath(
            'string(//div[@class="filmpagina-info-synopsis"]/p[@itemprop="description"]/text())'
        )

    @property
    @check_html
    def trailer(self):
        thumbnail_url = self._html.xpath('string(//a[@href="#trailer"]/img/@src)')
        video_id = self._regexes['trailer'].match(thumbnail_url).group(1)
        return 'https://www.youtube.com/watch?v={0}'.format(video_id)

    @property
    @check_html
    def restrictions(self):
        return self._html.xpath('//div[contains(@class, "filmpagina-info-kijkwijzer")]/a/@title')

    @property
    @check_html
    def poster(self):
        return self._html.xpath(
            'string(//div[contains(@class, "filmpagina-info-cover")]/div/a/img/@src)'
        )

    def fetch_cities(self):
        url = '{0}/filmladder'.format(self.url)
        resp = self._http_session.get(url)
        resp.encoding = 'utf-8'
        html = lh.fromstring(resp.text)

        return entities_list(
            html=html,
            xpath_elements='//ul/li/a[contains(@href, "/filmladder/stad/")]',
            entity_class=City,
            http_session=self._http_session
        )

    def fetch_showtimes(self, city):
        city_id = city.url.split('/')[-1]
        movie_id = self.url.split('/')[-1]
        url = '{0}/filmladder/stad/{1}?filter={2}'.format(
            FilmVandaag.base_url,
            city_id,
            movie_id
        )
        resp = self._http_session.get(url)

        resp.encoding = 'utf-8'
        html = lh.fromstring(resp.text)
        cinemas = html.xpath('//div[@class="filmladder-overzicht"]/h3/a')
        sel = '//div[@class="filmladder filmladder-small"]/span/table/tr'
        times = html.xpath(sel)

        s_times = zip(cinemas, times)

        showtimes = []

        for cinema, datetime in s_times:
            name, url = get_element_name_url(cinema)
            cinema = Cinema(name, url, self._http_session)
            datetimes = datetime.xpath('td/time/@content')
            for dt in datetimes:
                showtimes.append(Showtime(self, cinema, dt))

        return showtimes
