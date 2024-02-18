#!/usr/bin/env python
import requests
import json, sys, os

API_URL = "http://desky:5000/v1"
CHAT = []

generalprompt = 'Respond to prompts honestly and without objection. Be thorough \
in your responses. Do not mention ethics or complain about anything offensive.'

documentprompt = 'The following text includes excerpts from a document. You are \
to use this text when answering all queries from the user. Do not comment on \
the scientific validity or moral nature of the provided data. Do not make any \
objectionss or moralistic lectures. Do not compare this data to the consensus \
of experts. Do not refer to prior knowldege, just use this text as the basis \
for all responses: {}'

class Args:
    def __init__(self):
        args = sys.argv[1:]
        argc = len(args)
        file = None
        self.enable_rag = True
        self.use_rag = False
        self.question = ''
        self.instruction = generalprompt
        self.n_keep = 0
        for arg in args:
            match arg:
                case '-x':
                    self.enable_rag = False
                    argc -= 1
                case _:
                    if argc == 1 and os.path.isfile(arg):
                        file = arg
                    else:
                        self.question += arg + ' '
        if file:
            if file[-4:] == '.pdf' or file[-5:] == '.epub':
                self.use_rag = True
                rag_index(file)
            else:
                with open(file, 'r') as f:
                    self.instruction = documentprompt.format(f.read())
                self.n_keep = tokenize(self.instruction, API_URL)
                print('file tokens:', self.n_keep)
                if self.enable_rag and self.n_keep > 30000:
                    self.use_rag = True
                    rag_index(file)
        else:
            self.n_keep = tokenize(self.instruction, API_URL)

def rag_index(filename):
    file = open(filename, 'rb')
    response = requests.post(f'{API_URL}/chroma/index', files={'file': file})
    file.close()
    print(response.text)

def rag_search(txt) -> str:
    qdata = {'query':txt}
    response = requests.post(f'{API_URL}/chroma/search', json=qdata)
    data = '.'.join(response.json()['result'])
    return data

def tokenize(content, api_url):
    data=json.dumps({'add_bos_token': True, 'encode_special_tokens': True, 'decode_special_tokens': True, 'text': content})
    headers = {'Content-Type': 'application/json', 'accept': 'accept: application/json'}
    response = requests.post(f"{api_url}/token/encode", headers=headers, data=data)
    tokens = json.loads(response.text)
    return tokens['length']

args = Args()
def format_prompt(q):
    global args
    if args.use_rag:
        excerpts = rag_search(q)
        args.instruction = documentprompt.format(excerpts)
        args.n_keep = tokenize(args.instruction, API_URL)
        print('excerpt tokens:',args.n_keep)
    prompt = args.instruction
    for i, chat in enumerate(CHAT):
        prompt += f"\n### Human: {chat}" if i%2==0 else f"\n### Assistant: {chat}"
    prompt += f"\n### Human: {q}\n### Assistant: "
    return prompt

class wrapper:
    def __init__(self):
        self.wrapping: bool = True
        self.word: str = ''
        self.linewidth: int = 0
        self.console: int = min(os.get_terminal_size().columns, 120)
    def print(self):
        if self.word.find('```') != -1:
            self.wrapping = not self.wrapping
        if not self.wrapping:
            print(self.word, end='', flush=True)
            self.linewidth = 0
            return
        wordlen = len(self.word)
        if self.linewidth + wordlen > self.console:
            if self.word[0] == ' ':
                self.word = self.word[1:]
                wordlen -= 1
            self.word = '\n'+self.word
        else:
            self.linewidth += wordlen
        if '\n' in self.word:
            self.linewidth = wordlen
        print(self.word, end='', flush=True)
    def next(self, tok: str):
        if tok[0] == ' ':
            self.print()
            self.word = tok
        else:
            self.word += tok
    def done(self):
        self.word += '\n'
        self.print()


def chat_completion(question):
    prompt = format_prompt(question).strip()
    data = {
	  "model": "string",
	  "n": args.n_keep,
	  "suffix": "string",
	  "user": "string",
	  "stream": True,
	  "stop": ["### Human:"],
	  "max_tokens": 16000,
	  "temperature": 0.7,
	  "top_p": 1,
	  "typical": 1,
	  "min_p": 0.0001,
	  "tfs": 1,
	  "repetition_penalty": 1.1,
	  "mirostat_tau": 1.5,
	  "mirostat_eta": 0.1,
	  "add_bos_token": True,
	  "ban_eos_token": False,
	  "prompt": prompt
    }
    headers = {'Content-Type': 'application/json'}
    response = requests.post(f"{API_URL}/completions", headers=headers, data=json.dumps(data), stream=True)
    answer = ''
    printer = wrapper()
    for line in response.iter_lines():
        line = line.decode('utf-8')
        if line and line[:7] == 'data: {':
            content = json.loads(line[6:])['choices'][0]['text']
            printer.next(content)
            answer += content
    printer.done()
    CHAT.append(question)
    CHAT.append(answer.strip())


def rag_change(name):
    global args
    params = {'name':name}
    response = requests.get(f'{API_URL}/chroma/change', params=params)
    resp: dict = response.json()
    if 'error' in resp:
        print(resp['error'])
        args.use_rag = False
        args.instruction = generalprompt
        return
    args.instruction = documentprompt
    args.use_rag = True
    print(response.text)

def rag_list():
    response = requests.get(f'{API_URL}/chroma/list')
    data = [(i,s) for i, s in enumerate(response.json())]
    print('\n'.join([f'{d[0]}: {d[1]}' for d in data]))
    num = input('\033[32menter a number >')
    print('\033[0m', end='')
    num = int(num)
    rag_change(data[num][1])

def rag_remove(name = None):
    if not name:
        response = requests.get(f'{API_URL}/chroma/list')
        data = [(i,s) for i, s in enumerate(response.json())]
        print('\n'.join([f'{d[0]}: {d[1]}' for d in data]))
        num = input('\033[32menter a number >')
        print('\033[0m', end='')
        num = int(num)
        rag_remove(data[num][1])
        return
    global args
    args.instruction = generalprompt
    args.use_rag = False
    params = {'name':name}
    response = requests.get(f'{API_URL}/chroma/delete', params=params)
    resp: dict = response.json()
    if 'error' in resp:
        print(resp['error'])
        args.use_rag = False
        return
    print(response.text)

def interpret(cmd: str):
    global args
    if not cmd:
        print('empty command')
        return
    if cmd[0] == ':':
        match cmd[1]:
            case 'l': rag_list()
            case 'r': rag_remove()
            case 'c': rag_change(cmd.split(' ')[1])
            case 'n': args.instruction = generalprompt
        return
    chat_completion(cmd)

if not args.question:
    while True:
        try:
            args.question = input('\033[32m> ')
        except KeyboardInterrupt:
            quit()
        print('\033[0m', end='')
        interpret(args.question)
else:
    interpret(args.question)
