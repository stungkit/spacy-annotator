from IPython.display import clear_output, display, display_html
from ipywidgets import Button, HTML, HBox, Text, Output, Layout
import pandas as pd
import spacy
from spacy import displacy
from spacy.matcher import PhraseMatcher
from spacy.tokens import Span
import warnings


class Annotator:
    """
    Helper class for SpaCy based NER annotation.
    Parameters
    ----------
    model (spacy model) = SpaCy model for pre-annotation, optional.
    labels (list): list of named entity labels.
    delimiter (str): delimiter to separate entities in annotator. Default: ',' (comma).
    attr (str): include option to skip example while annotating. Default: True.
    include_skip (bool):
    """

    def __init__(
        self,
        *,
        model=None,
        labels,
        delimiter=",",
        attr="LOWER",  # "ORTH"
        include_skip=True,
    ):
        self.model = model
        if self.model is not None:
            self.nlp = model
        else:
            # TODO think of better solution for default?
            self.nlp = spacy.load("en_core_web_sm")
        self.labels = labels
        self.delimiter = delimiter
        self.attr = attr
        self.include_skip = include_skip

    @property
    def instructions(self):
        print(
            """
            \033[1mInstructions\033[0m \n
            For each entity type, input must be a DELIMITER separated string. \n
            If no entities in text, leave as is and press submit.
            Similarly, if no entities for a particular label, leave as is. \n
            Buttons: \n
            \t * submit inserts new annotation (or overwrites existing one if one is present). \n
            \t * skip moves forward and leaves empty string (or existing annotation if one is present). \n
            \t * finish terminates the annotation session.
            """
        )

    def __load_data(self, df, sample_size=1, shuffle=False, strata=None):
        """
        Helper function to load data into annotator and pre-process.
        Parameters
        ----------
        df (pandas dataframe): Dataframe with text to be labelled.
        sample_size (float): Size of the sample to be labelled. Default: 1.
        shuffle (bool): Option to shuffle data. Default: False.
        strata (dict): Dictionary {'key':'varname', 'cat1':prop, 'cat2':prop}, where 'key' is the name of the categorical variable to create strata,
            'cat1' and 'cat2' are the categories in the 'key' variables and 'prop' their proportion in the strata. Default: None.

        Returns
        -------
        Pre-processed dataframe to be labelled.
        """
        if "annotations" in df.columns:
            raise Exception(
                "Dataframe already has an annotations column, I don't want to overwrite this."
            )
        df_out = df.copy()
        if strata is not None:
            assert (
                sum([v for k, v in strata.items() if k != "key"]) == 1
            ), "The sum of proportions in strata is different from 1"
            df_out = (
                df_out.groupby(strata["key"], group_keys=False).apply(
                    lambda x: x.sample(
                        frac=(len(df) * sample_size * strata[x.name] / len(x))
                    )
                )
            ).reset_index(drop=True)

        elif (sample_size != 1) or shuffle:
            df_out = df_out.sample(frac=sample_size).reset_index(drop=True)
        df_out["annotations"] = ""
        return df_out

    def __add_annotation(self, df, col_text, current_index, annotations):
        spans = []
        for label, items in annotations.items():
            if items:
                item_list = [
                    i.strip() for i in items.split(self.delimiter) if i.strip() != ""
                ]
                print(item_list)
                matcher = PhraseMatcher(self.nlp.vocab, attr=self.attr)
                matcher.add(label, [self.nlp(item) for item in item_list])
                doc = self.nlp(df[col_text][current_index])
                matches = matcher(doc)
                print(matches)
                spans_new = []
                for match_id, start, end in matches:
                    span = Span(doc, start, end, label="")
                    spans_new.append(span)
                spans_filtered = spacy.util.filter_spans(spans_new)
                print(spans_filtered)
                spans.extend(
                    [(span.start_char, span.end_char, label) for span in spans_filtered]
                )
            else:
                continue
        entities = {"entities": spans}
        df.at[current_index, "annotations"] = (df[col_text][current_index], entities)

    def annotate(self, *, df, col_text, show_instructions=False, **kwargs):
        """
        Interactive widget for annotating a dataframe with examples.
        Parameters
        ----------
        df (pandas dataframe): Dataframe with text to be labelled.
        col_text (str): Column in pandas dataframe containing text to be labelled
        show_instructions (bool): Whether to print instructions. Default: False.
        **kwargs: Arguments for __load_data.

        Returns
        -------
        Labelled dataframe.
        """
        ## CHECK INPUTS ----

        assert (
            col_text is not None
        ), "Please provide a name of column containing text to be labelled."

        ## PRE-PROCESS DATA ---

        sample = self.__load_data(df, **kwargs)

        ## IPYWIDGET FUNCS ----

        def skip(btn):
            show_next()

        def finish(btn):
            for btn in buttons:
                btn.disabled = True
            return

        def submit(btn):
            self.__add_annotation(
                sample,
                col_text,
                current_index,
                {t.description: t.value for t in textboxes.values()},
            )
            for textbox in textboxes.values():
                textbox.value = ""
            show_next()

        def set_label_text():
            nonlocal count_label
            count_label.value = f"{current_index} examples annotated, {len(sample) - current_index} examples left"

        def reset_textarea():
            value = ";\n".join(f"{label}: insert" for label in self.labels) + ";"
            return value

        def show_next():
            nonlocal current_index
            current_index += 1
            set_label_text()
            if current_index >= len(sample):
                for btn in buttons:
                    btn.disabled = True
                with out:
                    clear_output(wait=True)
                    print("\033[1mThat's all folks!\033[0m\n")
            else:
                with out:
                    clear_output(wait=True)
                    print("\033[1mText:\033[0m")
                    doc = self.nlp(sample[col_text][current_index])
                    if self.model is None:
                        doc.ents = []
                    for label in textboxes.keys():
                        textboxes[label].value = ", ".join(
                            [ent.text for ent in doc.ents if ent.label_ == label]
                        )
                    ## NOTE displacy complains if there are no ents
                    # TODO remove null
                    with warnings.catch_warnings():
                        warnings.filterwarnings("ignore")
                        html = displacy.render(doc, style="ent")
                        display_html(html, raw=True)
                        print("")
            # TODO check out nlp.entity.beam_parse in spacy_annotator.pandas_annotations.annotate
            # understand threshold used by default, etc.
            # see https://stackoverflow.com/questions/46934523/spacy-ner-probability

        ## IPYWIDGET ----

        if show_instructions:
            self.instructions

        buttons = []

        btn = Button(description="submit", button_style="success")
        btn.on_click(submit)
        buttons.append(btn)

        if self.include_skip:
            btn = Button(description="skip", button_style="danger")
            btn.on_click(skip)
            buttons.append(btn)

        #         btn = Button(description='previous')
        #         # TODO add "previous" button, cf pigeonXT
        #         buttons.append(btn)

        btn = Button(description="finish")
        btn.on_click(finish)
        buttons.append(btn)

        current_index = -1
        count_label = HTML()

        set_label_text()
        display(count_label)

        textboxes = {
            label: Text(
                value="",
                description=f"{label}",
                placeholder=f"ent one{self.delimiter} ent two{self.delimiter} ent three",
                #     disabled=False,
                layout=Layout(width="auto"),
            )
            for label in self.labels
        }
        display(*textboxes.values())

        box = HBox(buttons)
        display(box)

        out = Output()
        display(out)

        show_next()

        return sample
